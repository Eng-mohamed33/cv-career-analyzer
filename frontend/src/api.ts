import type { CV, Job, Match, Session } from "./types";

const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";
const SESSION_KEY = "careerai.session";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function loadSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function saveSession(session: Session) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

async function request<T>(path: string, init: RequestInit = {}, authenticated = true): Promise<T> {
  const headers = new Headers(init.headers);
  const token = loadSession()?.token;
  if (authenticated && token) headers.set("Authorization", `Bearer ${token}`);
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("Cannot reach the server. Make sure the backend is running.", 0);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && authenticated) onUnauthorized?.();
    const detail = body?.detail;
    throw new ApiError(typeof detail === "string" ? detail : "Something went wrong. Please check your input.", response.status);
  }
  return body as T;
}

export const api = {
  authenticate: (mode: "login" | "register", name: string, password: string) =>
    request<Session>(`/auth/${mode}`, { method: "POST", body: JSON.stringify({ name, password }) }, false),
  me: () => request<{ name: string }>("/auth/me"),
  listCvs: () => request<CV[]>("/cvs"),
  uploadCv: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<CV>("/cvs", { method: "POST", body: form });
  },
  searchJobs: (query: string) => request<Job[]>(`/jobs/search${query.trim() ? `?query=${encodeURIComponent(query.trim())}` : ""}`),
  analyzeMatch: (cvId: string, job: Job) =>
    request<Match>("/jobs/match", {
      method: "POST",
      body: JSON.stringify({ cv_id: cvId, job_title: job.title, company: job.company, job_description: job.description }),
    }),
  listMatches: (cvId: string) => request<Match[]>(`/jobs/matches/${cvId}`),
};
