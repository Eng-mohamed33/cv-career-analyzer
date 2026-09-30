import { LogIn, UserPlus, Zap } from "lucide-react";
import type { FormEvent } from "react";
import type { AuthMode } from "../types";

type AuthScreenProps = {
  mode: AuthMode;
  setMode: (mode: AuthMode) => void;
  name: string;
  setName: (value: string) => void;
  password: string;
  setPassword: (value: string) => void;
  error: string;
  submitting: boolean;
  onSubmit: (event: FormEvent) => void;
};

export function AuthScreen({ mode, setMode, name, setName, password, setPassword, error, submitting, onSubmit }: AuthScreenProps) {
  const isLogin = mode === "login";
  return (
    <div className="auth-screen">
      <form className="auth-card" onSubmit={onSubmit}>
        <div className="brand auth-brand"><div className="brand-mark"><Zap size={18} /></div><span>CareerAI</span></div>
        <p className="eyebrow">{isLogin ? "WELCOME BACK" : "CREATE YOUR ACCOUNT"}</p>
        <h1>{isLogin ? "Sign in to your career workspace" : "Start your career journey"}</h1>
        <p className="muted">Manage your CV and find roles that fit your real skills.</p>
        <input aria-label="Your name" placeholder="Your name" autoComplete="username" value={name} onChange={(e) => setName(e.target.value)} required />
        <input aria-label="Password" type="password" placeholder="Password (6+ characters)" autoComplete={isLogin ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} minLength={6} required />
        {error && <div className="error-text" role="alert">{error}</div>}
        <button className="primary auth-button" type="submit" disabled={submitting}>
          {isLogin ? <><LogIn size={17} /> {submitting ? "Signing in..." : "Sign in"}</> : <><UserPlus size={17} /> {submitting ? "Creating account..." : "Create account"}</>}
        </button>
        <button type="button" className="text-button auth-switch" onClick={() => setMode(isLogin ? "register" : "login")}>
          {isLogin ? "Create a new account" : "I already have an account"}
        </button>
      </form>
    </div>
  );
}
