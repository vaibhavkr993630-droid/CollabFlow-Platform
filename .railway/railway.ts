import { defineRailway, github, image, postgres, preserve, project, redis, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("Postgres", { region: "ams" });
  const Redis = redis("Redis", { region: "ams" });
  Redis.deploy = { startCommand: "/bin/sh -c \"rm -rf $RAILWAY_VOLUME_MOUNT_PATH/lost+found/ && exec docker-entrypoint.sh redis-server --requirepass $REDIS_PASSWORD --save 60 1 --dir $RAILWAY_VOLUME_MOUNT_PATH\"" };

  const postgresVolume = volume("postgres-volume", { allowOnlineResize: true, region: "ams", sizeMB: 500 });
  const redisVolume = volume("redis-volume", { allowOnlineResize: true, region: "ams", sizeMB: 500 });
  const minioVolume = volume("minio-volume", { allowOnlineResize: true, region: "ams", sizeMB: 500 });

  const minio = service("minio", {
    // Pinned, and from Quay: Docker Hub's minio/minio is no longer served
    // (the same reason docker-compose.yml changed), and MinIO stopped
    // publishing images after this release.
    source: image("quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z"),
    replicas: { ams: 1 },
    volumeMounts: { "/data": minioVolume },
    env: { MINIO_ROOT_PASSWORD: preserve(), MINIO_ROOT_USER: preserve() },
    deploy: { startCommand: 'minio server /data --console-address ":9001"' },
    networking: { serviceDomains: { primary: { port: 9000 } } },
  });

  // Shared env across backend/worker/beat: same image, same dependencies, three
  // different start commands. DATABASE_URL is reconstructed with the asyncpg
  // driver prefix rather than referencing Postgres's own DATABASE_URL directly,
  // since that one is plain "postgresql://" (fine for psql/other clients, wrong
  // for this app's SQLAlchemy async engine).
  // Deliberately no secret literals in this file — it's committed to a public
  // repo. JWT_SECRET_KEY is generated and set directly via `railway variable
  // set` per service, outside this IaC file entirely, alongside
  // S3_PUBLIC_ENDPOINT_URL/SMTP_*/CORS_ORIGINS (which also can't be known until
  // minio's and the frontend's public domains exist). MINIO_ROOT_USER/PASSWORD
  // and the Postgres/Redis credentials referenced below via ${{Service.VAR}}
  // are Railway variable *references*, not literal values — safe to commit.
  const sharedEnv = {
    DATABASE_URL:
      "postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}",
    REDIS_URL: "${{Redis.REDIS_URL}}",
    ENVIRONMENT: "production",
    DEBUG: "false",
    S3_ENDPOINT_URL: "http://minio.railway.internal:9000",
    // Not a secret (it's a public URL, safe to commit) — minio's own public
    // domain, generated via `railway domain --service minio --port 9000`
    // since networking.serviceDomains on the minio service definition itself
    // didn't actually provision one (silent no-op observed during setup).
    S3_PUBLIC_ENDPOINT_URL: "https://minio-production-cb53.up.railway.app",
    S3_ACCESS_KEY: "${{minio.MINIO_ROOT_USER}}",
    S3_SECRET_KEY: "${{minio.MINIO_ROOT_PASSWORD}}",
    S3_BUCKET: "collabflow-attachments",
    // Declared here as preserve() specifically so a future `config apply`
    // doesn't treat it as undeclared drift and delete it — found this the
    // hard way: setting it via `railway variable set` alone, without also
    // declaring it here, made the very next `config plan` propose deleting
    // it. Actual secret value was set directly via `railway variable set`,
    // never written to this committed file.
    JWT_SECRET_KEY: preserve(),
    // Resend's SMTP relay. Host/port/user are fixed, documented values from
    // Resend's own docs, not secrets — the actual credential is the password,
    // which is the API key, set via `railway variable set` + preserve() below.
    // "onboarding@resend.dev" is Resend's shared testing sender, usable
    // without verifying a custom domain — free tier restricts it to only
    // deliver to the account's own verified email, which is fine for a demo.
    SMTP_HOST: "smtp.resend.com",
    // 2587, not the standard 587: Railway blocks outbound 25/465/587 entirely
    // (connection just times out — confirmed via a raw socket test from inside
    // the worker container, not an SMTP-level rejection). Resend documents
    // 2465/2587 as STARTTLS-equivalent alternates specifically for platforms
    // that block the standard ports; this app's smtplib code (starttls() then
    // login()) is already the right flow for either port, so only the port
    // number needed to change.
    SMTP_PORT: "2587",
    SMTP_FROM: "onboarding@resend.dev",
    SMTP_USER: "resend",
    SMTP_PASSWORD: preserve(),
    // The Vercel-deployed frontend's origin — not a secret, just needs to
    // match whatever domain the frontend actually deployed to.
    CORS_ORIGINS: '["https://frontend-flame-sigma-2zv4mlpsy0.vercel.app"]',
    // Where the password-reset link in an email points. Same origin as above:
    // the link is opened by a person in a browser, so it must be the frontend,
    // not this API. Left unset it would fall back to http://localhost:5173 and
    // every reset email sent from production would be a dead link.
    FRONTEND_URL: "https://frontend-flame-sigma-2zv4mlpsy0.vercel.app",
  };

  const backendSource = github("vaibhavkr993630-droid/CollabFlow-Platform", {
    branch: "main",
    rootDirectory: "backend",
  });
  const backendBuild = { builder: "DOCKERFILE" as const, dockerfilePath: "Dockerfile" };

  const backend = service("backend", {
    source: backendSource,
    build: backendBuild,
    env: sharedEnv,
    networking: { serviceDomains: { primary: { port: 8000 } } },
  });

  // Worker + beat combined into one service (Celery's -B flag runs an
  // embedded beat scheduler in the worker process) rather than the separate
  // services docker-compose.yml uses locally — Railway's free tier caps
  // service count per project, and this app only ever runs one worker
  // process anyway, so the usual reason to keep beat separate (multiple
  // worker replicas would each try to run their own beat, firing the
  // reminder job multiple times) doesn't apply here.
  const worker = service("worker", {
    source: backendSource,
    build: backendBuild,
    env: sharedEnv,
    // --concurrency=2, not Celery's default (CPU-count-based prefork pool):
    // that default read the *host* machine's full core count inside this
    // container (48, on whatever Railway node this landed on), not any
    // limit actually available to a free-tier container - forking that many
    // worker processes crash-looped the service. This app's task volume
    // (email sends, one daily reminder job) doesn't need real parallelism.
    deploy: {
      startCommand: "celery -A app.workers.celery_app worker -B --concurrency=2 --loglevel=info",
    },
  });

  return project("collabflow", {
    resources: [Postgres, Redis, minio, backend, worker, postgresVolume, redisVolume, minioVolume],
  });
});
