import { BarChart3, LayoutDashboard, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { ChangeEvent, FormEvent, MouseEvent } from "react";
import { ApiError, api, clearSession, loadSession, saveSession, setUnauthorizedHandler } from "./api";
import { AuthScreen } from "./components/AuthScreen";
import { Dashboard } from "./components/Dashboard";
import { JobsPage } from "./components/JobsPage";
import type { AuthMode, CV, Job, Match, Page, Session } from "./types";

const errorMessage = (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback);

export function App() {
  const [session, setSession] = useState<Session | null>(() => loadSession());
  const [booting, setBooting] = useState(() => loadSession() !== null);
  const [page, setPage] = useState<Page>("dashboard");
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [cv, setCv] = useState<CV | null>(null);
  const [uploading, setUploading] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsLoaded, setJobsLoaded] = useState(false);
  const [matches, setMatches] = useState<Match[]>([]);
  const [query, setQuery] = useState("");
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [match, setMatch] = useState<Match | null>(null);
  const [analyzingId, setAnalyzingId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const resetWorkspace = useCallback(() => {
    setCv(null); setJobs([]); setJobsLoaded(false); setMatches([]); setSelectedJob(null); setMatch(null);
    setError(""); setPage("dashboard");
  }, []);

  const logout = useCallback(() => {
    clearSession(); setSession(null); setPassword(""); resetWorkspace();
  }, [resetWorkspace]);

  const loadWorkspace = useCallback(async () => {
    const savedCvs = await api.listCvs();
    const latest = savedCvs[0] ?? null;
    setCv(latest);
    setMatches(latest ? await api.listMatches(latest.id) : []);
  }, []);

  // An expired or invalid token anywhere in the app sends the user back to sign in.
  useEffect(() => { setUnauthorizedHandler(logout); return () => setUnauthorizedHandler(null); }, [logout]);

  // Restore a saved session: verify the token with the server, then load the user's data.
  useEffect(() => {
    if (!booting) return;
    let cancelled = false;
    (async () => {
      try { await api.me(); await loadWorkspace(); }
      catch (bootError) {
        // An invalid/expired token (401) is handled by the unauthorized handler, which signs out.
        // A network or server error must NOT sign the user out, or restarting the backend loses the session.
        if (!cancelled && !(bootError instanceof ApiError && bootError.status === 401)) setError(errorMessage(bootError, "Could not load your workspace"));
      }
      finally { if (!cancelled) setBooting(false); }
    })();
    return () => { cancelled = true; };
  }, [booting, loadWorkspace]);

  const searchJobs = useCallback(async () => {
    setError(""); setJobsLoading(true);
    try { setJobs(await api.searchJobs(query)); }
    catch (searchError) { setError(errorMessage(searchError, "Could not load jobs")); }
    finally { setJobsLoading(false); setJobsLoaded(true); }
  }, [query]);

  // Load listings the first time the jobs page opens (jobsLoaded stops retry loops after a failure).
  useEffect(() => { if (session && page === "jobs" && !jobsLoaded) void searchJobs(); }, [session, page, jobsLoaded, searchJobs]);

  async function submitAuth(event: FormEvent) {
    event.preventDefault(); setAuthError(""); setAuthSubmitting(true);
    try {
      const authenticated = await api.authenticate(authMode, name.trim(), password);
      saveSession(authenticated); setSession(authenticated); setPassword("");
      try { await loadWorkspace(); }
      catch (workspaceError) { setError(errorMessage(workspaceError, "Could not load your workspace")); }
    } catch (authErr) { setAuthError(errorMessage(authErr, "Authentication failed")); }
    finally { setAuthSubmitting(false); }
  }

  async function uploadCv(event: ChangeEvent<HTMLInputElement>) {
    const input = event.target;
    const file = input.files?.[0]; if (!file) return;
    setUploading(true); setError("");
    try {
      const uploaded = await api.uploadCv(file);
      setCv(uploaded); setMatches([]); setMatch(null); setSelectedJob(null); setPage("dashboard");
    } catch (uploadError) { setError(errorMessage(uploadError, "CV upload failed")); }
    finally { setUploading(false); input.value = ""; }
  }

  async function analyzeMatch(job: Job) {
    if (!cv) { setError("Upload a CV first so the AI can compare it with the job."); return; }
    setError(""); setSelectedJob(job); setMatch(null); setAnalyzingId(job.id);
    try {
      const result = await api.analyzeMatch(cv.id, job);
      setMatch(result);
      setMatches((old) => [result, ...old.filter((item) => !(item.job_title === result.job_title && item.company === result.company))]);
    } catch (matchError) { setError(errorMessage(matchError, "Could not analyze this job")); }
    finally { setAnalyzingId(null); }
  }

  function findJobs(searchTerm: string) {
    // Reset the listing so the jobs page loads fresh results for this term.
    setError(""); setQuery(searchTerm); setJobs([]); setJobsLoaded(false); setSelectedJob(null); setMatch(null); setPage("jobs");
  }

  function navigate(target: Page) {
    return (event: MouseEvent) => { event.preventDefault(); setError(""); setPage(target); };
  }

  if (booting) return null;
  if (!session) {
    return <AuthScreen mode={authMode} setMode={setAuthMode} name={name} setName={setName} password={password} setPassword={setPassword} error={authError} submitting={authSubmitting} onSubmit={submitAuth} />;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><Zap size={18} /></div><span>CareerAI</span></div>
        <nav>
          <a href="#dashboard" className={page === "dashboard" ? "active" : ""} aria-current={page === "dashboard" ? "page" : undefined} onClick={navigate("dashboard")}><LayoutDashboard size={18} /> Dashboard</a>
          <a href="#jobs" className={page === "jobs" ? "active" : ""} aria-current={page === "jobs" ? "page" : undefined} onClick={navigate("jobs")}><BarChart3 size={18} /> Job Matches</a>
        </nav>
        <div className="sidebar-bottom">
          <div className="avatar">{session.name.slice(0, 2).toUpperCase()}</div>
          <div><strong>{session.name}</strong><button className="text-button signout" onClick={logout}>Sign out</button></div>
        </div>
      </aside>
      <main className="main-content">
        {error && <div className="error-banner" role="alert">{error}</div>}
        {page === "dashboard" && <Dashboard name={session.name} cv={cv} matchCount={matches.length} uploading={uploading} uploadCv={uploadCv} setPage={setPage} findJobs={findJobs} />}
        {page === "jobs" && <JobsPage query={query} setQuery={setQuery} jobs={jobs} jobsLoading={jobsLoading} jobsLoaded={jobsLoaded} searchJobs={searchJobs} selectedJob={selectedJob} analyzingId={analyzingId} analyzeMatch={analyzeMatch} match={match} matchCount={matches.length} />}
      </main>
    </div>
  );
}
