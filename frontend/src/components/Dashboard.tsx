import { FileText, Upload } from "lucide-react";
import type { ChangeEvent } from "react";
import type { CV, Page } from "../types";
import { Stat } from "./Stat";

type DashboardProps = {
  name: string;
  cv: CV | null;
  matchCount: number;
  uploading: boolean;
  uploadCv: (event: ChangeEvent<HTMLInputElement>) => void;
  setPage: (page: Page) => void;
  findJobs: (searchTerm: string) => void;
};

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export function Dashboard({ name, cv, matchCount, uploading, uploadCv, setPage, findJobs }: DashboardProps) {
  return (
    <>
      <header>
        <div>
          <p className="eyebrow">YOUR CAREER WORKSPACE</p>
          <h1>{greeting()}, {name} 👋</h1>
          <p className="muted">Upload your CV to see your profile and find suitable jobs.</p>
        </div>
      </header>
      <section className="stats-grid">
        <Stat label="CV SCORE" value={cv ? `${cv.score}` : "—"} suffix={cv ? "/100" : undefined} trend={cv ? "Keyword-based estimate" : "Upload a CV first"} />
        <Stat label="JOB MATCHES" value={cv ? `${matchCount}` : "—"} trend={matchCount ? "Jobs you analyzed" : "Choose a job to analyze"} />
        <Stat label="SKILLS FOUND" value={cv ? `${cv.skills.length}` : "—"} trend={cv ? "Extracted from your CV" : "Upload a CV first"} />
      </section>
      <div className="panel dashboard-upload">
        <label className="dropzone large-drop" htmlFor="cv-upload">
          <Upload size={25} />
          <strong>{uploading ? "Analyzing your CV..." : cv ? "Upload a newer CV" : "Upload your CV"}</strong>
          <span>PDF files only, up to 5 MB · your analysis will be based on its actual content</span>
        </label>
        <input id="cv-upload" className="visually-hidden" type="file" accept="application/pdf" disabled={uploading} onChange={uploadCv} />
        {cv && (
          <>
            <div className="cv-summary">
              <FileText size={22} />
              <div><strong>{cv.filename}</strong><small>Score: {cv.score}/100</small></div>
              <button className="primary" onClick={() => setPage("jobs")}>Choose a job</button>
            </div>
            {cv.skills.length > 0 && (
              <div className="chip-row" aria-label="Skills found in your CV">
                {cv.skills.map((skill) => <span className="skill-chip green-chip" key={skill}>{skill}</span>)}
              </div>
            )}
          </>
        )}
      </div>
      {cv && (
        <section className="panel tracks-panel">
          <div className="section-heading">
            <div><p className="eyebrow">SUGGESTED CAREER PATHS</p><h2>Roles that fit your skills</h2></div>
          </div>
          {cv.tracks.length === 0 ? (
            <p className="muted">Not enough skills were found to suggest a path yet. Add a skills section and link your GitHub in your CV.</p>
          ) : (
            <div className="track-grid">
              {cv.tracks.map((track) => (
                <div className="track-card" key={track.name}>
                  <div className="track-head"><strong>{track.name}</strong><span className="track-score">{track.score}%</span></div>
                  <div className="track-bar" role="img" aria-label={`${track.score}% skill fit`}><span style={{ width: `${track.score}%` }} /></div>
                  <div className="chip-row tight">
                    {track.matched_skills.map((skill) => <span className="skill-chip green-chip" key={skill}>✓ {skill}</span>)}
                  </div>
                  {track.missing_skills.length > 0 && (
                    <>
                      <small className="muted">To strengthen this path</small>
                      <div className="chip-row tight">
                        {track.missing_skills.map((skill) => <span className="skill-chip orange-chip" key={skill}>+ {skill}</span>)}
                      </div>
                    </>
                  )}
                  <button className="text-button track-action" onClick={() => findJobs(track.search_term)}>Find {track.name} jobs →</button>
                </div>
              ))}
            </div>
          )}
          <small className="muted track-note">Fit is based on the skills detected in your CV and GitHub, not a guarantee of hiring.</small>
        </section>
      )}
    </>
  );
}
