import { createClient } from '@/lib/supabase/server'

type HttpMethod = 'GET' | 'POST' | 'DELETE' | 'PATCH'

interface RequestOptions {
  body?: unknown
  headers?: Record<string, string>
}

class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function getAccessToken(): Promise<string | null> {
  try {
    const supabase = await createClient()
    const {
      data: { session },
    } = await supabase.auth.getSession()
    return session?.access_token ?? null
  } catch {
    return null
  }
}

async function request<T>(
  method: HttpMethod,
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL
  if (!baseUrl) {
    throw new ApiError('API base URL is not configured', 500)
  }

  const token = await getAccessToken()

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  })

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    try {
      const errorBody = await response.json() as { detail?: string; error?: string }
      message = errorBody.detail ?? errorBody.error ?? message
    } catch {
      // Response body is not JSON — use the default message
    }
    throw new ApiError(message, response.status)
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export const apiClient = {
  get<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>('GET', path, options)
  },

  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>('POST', path, { ...options, body })
  },

  delete<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>('DELETE', path, options)
  },

  patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>('PATCH', path, { ...options, body })
  },
}
