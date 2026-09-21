import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { z } from 'zod'

import * as authApi from '../api/auth'

const schema = z.object({
  email: z.string().email('Enter a valid email'),
})

type FormValues = z.infer<typeof schema>

export default function ForgotPasswordPage() {
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  async function onSubmit(values: FormValues) {
    setServerError(null)
    try {
      await authApi.forgotPassword(values.email)
      // The API answers identically whether or not the address has an account, so this
      // screen deliberately never says "we found you" or "we didn't" — it can't know.
      setSentTo(values.email)
    } catch {
      setServerError('Something went wrong. Please try again.')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
        {sentTo ? (
          <>
            <h1 className="mb-3 text-xl font-semibold text-gray-900">Check your email</h1>
            <p className="text-sm text-gray-600">
              If an account exists for <span className="font-medium">{sentTo}</span>, we've sent a
              link to reset its password. The link works once and expires after a short time.
            </p>
            <button
              type="button"
              onClick={() => setSentTo(null)}
              className="mt-4 text-sm font-medium text-brand-600 hover:underline"
            >
              Use a different email
            </button>
          </>
        ) : (
          <>
            <h1 className="mb-2 text-xl font-semibold text-gray-900">Forgot your password?</h1>
            <p className="mb-6 text-sm text-gray-500">
              Enter your account email and we'll send you a link to choose a new one.
            </p>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
              <div>
                <label htmlFor="email" className="mb-1 block text-sm font-medium text-gray-700">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500 focus:outline-none"
                  {...register('email')}
                />
                {errors.email && (
                  <p className="mt-1 text-xs text-red-600">{errors.email.message}</p>
                )}
              </div>

              {serverError && <p className="text-sm text-red-600">{serverError}</p>}

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {isSubmitting ? 'Sending…' : 'Send reset link'}
              </button>
            </form>
          </>
        )}

        <p className="mt-4 text-center text-sm text-gray-500">
          <Link to="/login" className="font-medium text-brand-600 hover:underline">
            Back to log in
          </Link>
        </p>
      </div>
    </div>
  )
}
