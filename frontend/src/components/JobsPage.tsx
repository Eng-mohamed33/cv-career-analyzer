import { BarChart3, Search } from "lucide-react";
import type { Job, Match } from "../types";

type JobsPageProps = {
  query: string;
  setQuery: (value: string) => void;
  jobs: Job[];
  jobsLoading: boolean;
  jobsLoaded: boolean;
  searchJobs: () => void;
  selectedJob: Job | null;
  analyzingId: string | null;
  analyzeMatch: (job: Job) => void;
  match: Match | null;
  matchCount: number;
};

export function JobsPage({ query, setQuery, jobs, jobsLoading, jobsLoaded, searchJobs, selectedJob, analyzingId, analyzeMatch, match, matchCount }: JobsPageProps) {
  return (
    <>
      <header>
        <div>
          <p className="eyebrow">JOB MATCHES</p>
          <h1>Find your next role</h1>
          <p className="muted">Choose a job and compare it with your CV.</p>
        </div>
      </header>
      <div className="job-search">
        <Search size={18} />
        <input aria-label="Search jobs" placeholder="Search by skill or role, e.g. Python" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchJobs()} />
        <button className="primary" onClick={searchJobs} disabled={jobsLoading}>{jobsLoading ? "Searching..." : "Search jobs"}</button>
      </div>
      <div className="jobs-layout">
        <div className="panel jobs-list">
          <div className="section-heading">
            <div><p className="eyebrow">FREE LIVE LISTINGS</p><h2>Choose a job</h2></div>
            <small>Jobicy</small>
          </div>
          {jobsLoaded && !jobsLoading && jobs.length === 0 && (
            <div className="empty-matches"><strong>No jobs found</strong><span>Try a different keyword, like a skill from your CV.</span></div>
          )}
          {jobs.map((job) => (
            <div className={`job-item ${selectedJob?.id === job.id ? "selected" : ""}`} key={job.id}>
              <div><strong>{job.title}</strong><small>{job.company}</small></div>
              <button className="text-button" onClick={() => analyzeMatch(job)} disabled={analyzingId !== null}>
                {analyzingId === job.id ? "Analyzing..." : "Analyze match"}
              </button>
            </div>
          ))}
        </div>
        <div className="panel match-result">
          {match ? (
            <>
              <p className="eyebrow">AI JOB ANALYSIS</p>
              <h2>{match.job_title}</h2>
              <p className="muted">{match.company}</p>
              <div className="match-score-box"><strong>{match.score}%</strong><span>CV match</span></div>
              <div className="match-columns">
                <div><b>Matched skills</b>{match.matched_skills.map((skill) => <span className="skill-chip green-chip" key={skill}>✓ {skill}</span>)}</div>
                <div><b>Missing skills</b>{match.missing_skills.map((skill) => <span className="skill-chip orange-chip" key={skill}>+ {skill}</span>)}</div>
              </div>
              <p className="recommendation">{match.recommendations[0]}</p>
              {selectedJob && <a className="primary apply-link" href={selectedJob.url} target="_blank" rel="noreferrer">View job ↗</a>}
            </>
          ) : (
            <div className="empty-matches"><BarChart3 size={25} /><strong>Select a job to analyze it</strong><span>The match score will appear here.</span></div>
          )}
        </div>
      </div>
      {matchCount > 0 && <p className="muted previous-matches">Jobs analyzed for this CV: {matchCount}</p>}
    </>
  );
}
