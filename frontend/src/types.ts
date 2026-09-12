/** API types — mirrors backend/app/models.py. */

export type Status = "applied" | "interview" | "offer" | "reject";
export type DraftType = "cover_letter" | "follow_up_email" | "referral_request" | "linkedin_message";
export type DraftStatus = "draft" | "sent";
export type NudgeStatus = "pending" | "done" | "dismissed";

export interface StatusChange {
  from_status: Status | null;
  to_status: Status;
  at: string;
  note: string;
}

export interface Application {
  id: string;
  uid: string;
  external_id: string | null;
  company: string;
  role: string;
  location: string;
  job_type: string;
  description: string;
  skills: string[];
  posting_url: string;
  posting_from: string | null;
  posting_to: string | null;
  applied_at: string;
  status: Status;
  status_history: StatusChange[];
  last_activity_at: string;
  source: "manual" | "import" | "capture";
  notes: string;
  contact_name: string;
  contact_email: string;
  interview_at: string | null;
  prep_pack: PrepPack | null;
  created_at: string;
  updated_at: string;
}

export interface PrepQuestion {
  question: string;
  why_they_ask: string;
  how_to_answer: string;
}

export interface PrepStory {
  title: string;
  outline: string;
  metric: string;
}

export interface PrepPack {
  questions: PrepQuestion[];
  stories: PrepStory[];
  questions_to_ask: string[];
  model: string;
  generated_at: string;
}

export interface CapturedPosting {
  role: string;
  company: string;
  location: string;
  job_type: string;
  skills: string[];
  description: string;
  posting_url: string;
}

export interface Draft {
  id: string;
  application_id: string;
  external_id: string | null;
  type: DraftType;
  subject: string;
  contents: string;
  status: DraftStatus;
  source: "generated" | "imported" | "edited";
  model: string;
  grounded_on: string[];
  created_at: string;
  updated_at: string;
}

export interface Nudge {
  id: string;
  application_id: string;
  rule: "follow_up" | "interview_thank_you" | "offer_response" | "reject_feedback";
  touch: number;
  headline: string;
  detail: string;
  due_at: string;
  status: NudgeStatus;
  draft_id: string | null;
  created_at: string;
}

export type EngineSource = "your_key" | "free_credits" | "key_required" | "demo";

export interface Profile {
  uid: string;
  name: string;
  headline: string;
  years_experience: number;
  skills: string[];
  tone: string;
  achievements: string;
  style_rules: string;
  onboarded: boolean;
  points: number;
  level: string;
  gemini_key_masked: string | null;
  free_remaining: number;
  engine: EngineSource;
  weekly_goal: number;
  push_enabled: boolean;
}

export interface RowError {
  row: number;
  reason: string;
}

export interface FileReport {
  filename: string;
  total_rows: number;
  accepted: number;
  updated: number;
  rejected: RowError[];
}

export interface ImportReport {
  id: string;
  postings: FileReport;
  drafts: FileReport;
  linked_drafts: number;
  orphaned_drafts: number;
  relinked_drafts: number;
  embedded: number;
  duration_ms: number;
  created_at: string;
}

export interface ScanReport {
  scanned: number;
  nudges_created: number;
  drafts_generated: number;
  duration_ms: number;
}

export interface WeekActivity {
  week_start: string;
  applications: number;
  drafts: number;
  status_changes: number;
}

export interface Analytics {
  total_applications: number;
  by_status: Record<Status, number>;
  reached_interview: number;
  reached_offer: number;
  interview_rate: number;
  offer_rate: number;
  median_days_to_interview: number | null;
  ghosted: number;
  ghost_rate: number;
  drafts_total: number;
  drafts_sent: number;
  nudges_pending: number;
  nudges_actioned: number;
  weekly: WeekActivity[];
  followed_up: number;
  followup_interview_rate: number | null;
  no_followup_interview_rate: number | null;
  followup_lift: number | null;
}

export interface AppConfig {
  mode: "demo" | "live";
  firebase: Record<string, string>;
  push_vapid_key: string;
  cadence: {
    follow_up_backoff_days: number[];
    interview_thank_you_days: number;
    offer_response_days: number;
    reject_feedback_days: number;
    ghost_after_days: number;
  };
}

export const STATUSES: Status[] = ["applied", "interview", "offer", "reject"];

export const STATUS_LABEL: Record<Status, string> = {
  applied: "Applied",
  interview: "Interview",
  offer: "Offer",
  reject: "Reject",
};

export const DRAFT_TYPE_LABEL: Record<DraftType, string> = {
  cover_letter: "Cover letter",
  follow_up_email: "Follow-up email",
  referral_request: "Referral request",
  linkedin_message: "LinkedIn message",
};
