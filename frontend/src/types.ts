export type Page = "dashboard" | "jobs";
export type AuthMode = "login" | "register";
export type Session = { name: string; token: string };
export type Track = { name: string; score: number; matched_skills: string[]; missing_skills: string[]; search_term: string };
export type CV = { id: string; filename: string; score: number; skills: string[]; tracks: Track[] };
export type Job = { id: string; title: string; company: string; location: string; description: string; url: string; match_score: number };
export type Match = { job_title: string; company: string; score: number; matched_skills: string[]; missing_skills: string[]; recommendations: string[] };
