import { zodResolver } from '@hookform/resolvers/zod'
import { isAxiosError } from 'axios'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useSearchParams } from 'react-router-dom'
import { z } from 'zod'

import * as authApi from '../api/auth'

const schema = z
  .object({
    new_password: z.string().min(8, 'Password must be at least 8 characters'),
    confirm_password: z.string().min(1, 'Please confirm your new password'),
  })
  .refine((data) => data.new_password === data.confirm_password, {
    message: 'Passwords do not match',
    path: ['confirm_password'],
  })

type FormValues = z.infer<typeof schema>

const inputClass =
  'w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500 focus:outline-none'

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
        {children}
      </div>
    </div>
  )
}

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [done, setDone] = useState(false)
  const [linkRejected, setLinkRejected] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  async function onSubmit(values: FormValues) {
    if (!token) return
    setServerError(null)
    try {
      await authApi.resetPassword({ token, new_password: values.new_password })
      setDone(true)
    } catch (error) {
      // 400 is the API saying the link itself is bad (expired, already used, tampered with).
      if (isAxiosError(error) && error.response?.status === 400) {
        setLinkRejected(true)
      } else {
        setServerError('Something went wrong. Please try again.')
      }
    }
  }

  if (!token || linkRejected) {
    return (
      <Card>
        <h1 className="mb-3 text-xl font-semibold text-gray-900">
          This reset link isn't valid
        </h1>
        <p className="text-sm text-gray-600">
          It may have expired, or it may already have been used. Reset links work once.
        </p>
        <Link
          to="/forgot-password"
          className="mt-4 inline-block text-sm font-medium text-brand-600 hover:underline"
        >
          Request a new link
        </Link>
      </Card>
    )
  }

  if (done) {
    return (
      <Card>
        <h1 className="mb-3 text-xl font-semibold text-gray-900">Password updated</h1>
        <p className="text-sm text-gray-600">Your password has been changed. You can log in now.</p>
        <Link
          to="/login"
          className="mt-4 block w-full rounded-lg bg-brand-600 px-4 py-2 text-center text-sm font-medium text-white hover:bg-brand-700"
        >
          Log in
        </Link>
      </Card>
    )
  }

  return (
    <Card>
      <h1 className="mb-6 text-xl font-semibold text-gray-900">Choose a new password</h1>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <div>
          <label htmlFor="new_password" className="mb-1 block text-sm font-medium text-gray-700">
            New password
          </label>
          <input
            id="new_password"
            type="password"
            autoComplete="new-password"
            className={inputClass}
            {...register('new_password')}
          />
          {errors.new_password && (
            <p className="mt-1 text-xs text-red-600">{errors.new_password.message}</p>
          )}
        </div>

        <div>
          <label
            htmlFor="confirm_password"
            className="mb-1 block text-sm font-medium text-gray-700"
          >
            Confirm new password
          </label>
          <input
            id="confirm_password"
            type="password"
            autoComplete="new-password"
            className={inputClass}
            {...register('confirm_password')}
          />
          {errors.confirm_password && (
            <p className="mt-1 text-xs text-red-600">{errors.confirm_password.message}</p>
          )}
        </div>

        {serverError && <p className="text-sm text-red-600">{serverError}</p>}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {isSubmitting ? 'Updating…' : 'Update password'}
        </button>
      </form>
    </Card>
  )
}
