import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  Bot,
  BriefcaseBusiness,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  DollarSign,
  ExternalLink,
  FileText,
  GitBranch,
  GraduationCap,
  LineChart,
  RefreshCw,
  Search,
  Server,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  DashboardV2Metric,
  DashboardV2Response,
  DeploymentStatusSummary,
  GeneratedReportItem,
  GeneratedReportLatestEnvelope,
  ReportFileSummary,
  ReportsProjectSummary,
  ReportsResponse,
  ReportsTaskSummary,
} from "@/lib/api";
import { Button } from "@nous-research/ui/ui/components/button";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Stats } from "@nous-research/ui/ui/components/stats";
import { usePageHeader } from "@/contexts/usePageHeader";
import { PluginSlot } from "@/plugins";

type DataSource = "dashboard-v2" | "reports-fallback";

interface DashboardViewModel {
  source: DataSource;
  generatedAt?: number | null;
  reports: ReportsResponse;
  executiveBriefing: {
    headline: string;
    status: string;
    summary: string;
    highlights: string[];
    risks: string[];
    nextActions: string[];
  };
  boardHealth: {
    metrics: DashboardV2Metric[];
    statusCounts: Record<string, number>;
  };
  portfolioHealth: {
    metrics: DashboardV2Metric[];
    projects: ReportsProjectSummary[];
  };
  careerProgress: {
    status?: string | null;
    summary?: string | null;
    milestones: DashboardV2Metric[];
  };
  engineeringMetrics: {
    metrics: DashboardV2Metric[];
    recentCompleted: ReportsTaskSummary[];
    reviewRequired: ReportsTaskSummary[];
    deploymentStatus: DeploymentStatusSummary[];
    githubActivity: ReportFileSummary[];
  };
  agentMetrics: {
    metrics: DashboardV2Metric[];
    modelBreakdown: DashboardV2Metric[];
    notes: string[];
  };
  financialMetrics: {
    metrics: DashboardV2Metric[];
    notes: string[];
  };
  weeklyReports: {
    completionReports: ReportFileSummary[];
    qaFindings: ReportFileSummary[];
    latestReports: ReportFileSummary[];
  };
  generatedReports: GeneratedReportLatestEnvelope[];
}


const EXECUTIVE_AREA_TARGETS = {
  careerDevelopment: "career-development",
  bureauos: "bureauos",
  engineeringBrand: "engineering-brand",
  artistManagement: "artist-management",
  venturePortfolio: "venture-portfolio",
  hermesOperations: "hermes-operations",
} as const;

const EXECUTIVE_AREA_HREFS = {
  careerDevelopment: "#career-development",
  bureauos: "#bureauos",
  engineeringBrand: "#engineering-brand",
  artistManagement: "#artist-management",
  venturePortfolio: "#venture-portfolio",
  hermesOperations: "#hermes-operations",
} as const;

function kanbanTaskHref(taskId: string, board?: string | null): string {
  const params = new URLSearchParams({ task: taskId });
  if (board) params.set("board", board);
  return `/kanban?${params.toString()}`;
}

function boardHref(board: string): string {
  const params = new URLSearchParams({ board });
  return `/kanban?${params.toString()}`;
}

function profileHref(profile?: string | null): string | null {
  if (!profile) return null;
  return `/profiles?profile=${encodeURIComponent(profile)}`;
}

function reportDetailHref(report: ReportFileSummary): string {
  return `/reports?report=${encodeURIComponent(report.id)}`;
}

function generatedReportDetailHref(type: string): string {
  return `/reports/generated/${encodeURIComponent(type)}`;
}

function formatDate(value?: number | null): string {
  if (!value) return "—";
  return new Date(value * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusTone(status?: string | null): string {
  switch ((status || "").toLowerCase()) {
    case "healthy":
    case "available":
    case "on track":
    case "done":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-600";
    case "degraded":
    case "review":
    case "blocked":
    case "attention":
      return "border-amber-500/30 bg-amber-500/10 text-amber-600";
    case "failed":
    case "at risk":
      return "border-destructive/30 bg-destructive/10 text-destructive";
    default:
      return "border-border bg-secondary/40 text-muted-foreground";
  }
}

function isMissingDashboardEndpoint(err: unknown): boolean {
  return err instanceof Error && /^(404|405):/.test(err.message);
}

function asArray<T>(value?: T[] | null): T[] {
  return Array.isArray(value) ? value : [];
}

function metric(label: string, value: string | number | null | undefined, detail?: string | null): DashboardV2Metric {
  return { label, value: value ?? 0, detail };
}

function createEmptyReports(project: string, q: string): ReportsResponse {
  return {
    filters: { project, q },
    summary: {
      completed_tasks: 0,
      review_required: 0,
      active_projects: 0,
      completion_reports: 0,
      qa_findings: 0,
      deployment_updates: 0,
      github_updates: 0,
      status_counts: {},
    },
    recent_completed: [],
    review_required: [],
    active_projects: [],
    completion_reports: [],
    qa_findings: [],
    deployment_status: [],
    github_activity: [],
    generated_at: Math.floor(Date.now() / 1000),
  };
}

function reportsFromDashboard(data: DashboardV2Response, project: string, q: string): ReportsResponse {
  if (data.legacy_reports) return data.legacy_reports;

  const briefing = data.executive_briefing ?? {};
  const engineering = data.engineering_metrics ?? {};
  const weekly = data.weekly_reports ?? {};
  const board = data.board_health ?? {};
  const portfolio = data.portfolio_health ?? {};
  const portfolioItems = asArray(portfolio.projects).length ? asArray(portfolio.projects) : asArray(data.portfolio_ventures);
  const projects = portfolioItems.map((item) => ({
    project: item.project,
    active_tasks: item.active_tasks ?? 0,
    blocked_tasks: item.blocked_tasks ?? 0,
    review_required: item.review_required ?? 0,
    latest_activity_at: item.latest_activity_at ?? data.generated_at ?? 0,
  }));
  const latestReports = asArray(weekly.latest_reports).length ? asArray(weekly.latest_reports) : asArray(weekly.latest);
  const completionReports = asArray(weekly.completion_reports).length
    ? asArray(weekly.completion_reports)
    : latestReports.filter((item) => item.kind === "completion" || item.kind === "completion_report");
  const qaFindings = asArray(weekly.qa_findings).length
    ? asArray(weekly.qa_findings)
    : latestReports.filter((item) => item.kind === "qa" || item.kind === "qa_finding");
  const recentCompleted = asArray(engineering.recent_completed).length
    ? asArray(engineering.recent_completed)
    : asArray(briefing.completed_tasks);
  const reviewRequired = asArray(briefing.review_required_tasks);

  return {
    filters: { project, q },
    summary: {
      completed_tasks: board.completed_tasks ?? engineering.completed_tasks ?? recentCompleted.length,
      review_required: board.review_required ?? engineering.review_required ?? reviewRequired.length,
      active_projects: portfolio.active_projects ?? projects.length,
      completion_reports: completionReports.length,
      qa_findings: qaFindings.length,
      deployment_updates: asArray(engineering.deployment_status).length,
      github_updates: asArray(engineering.github_activity).length,
      status_counts: board.status_counts ?? {},
    },
    recent_completed: recentCompleted,
    review_required: reviewRequired,
    active_projects: projects,
    completion_reports: completionReports,
    qa_findings: qaFindings,
    deployment_status: asArray(engineering.deployment_status),
    github_activity: asArray(engineering.github_activity),
    generated_at: data.generated_at ?? Math.floor(Date.now() / 1000),
  };
}

function financialNotes(value: DashboardV2Response["financial_metrics"]): string[] {
  const notes = value?.notes;
  if (Array.isArray(notes)) return notes;
  if (typeof notes === "string" && notes.trim()) return [notes];
  return [];
}

function buildFallbackDashboard(reports: ReportsResponse): DashboardViewModel {
  const latestReports = [...reports.completion_reports, ...reports.qa_findings, ...reports.github_activity]
    .sort((a, b) => (b.updated_at ?? 0) - (a.updated_at ?? 0))
    .slice(0, 6);

  return {
    source: "reports-fallback",
    generatedAt: reports.generated_at,
    reports,
    executiveBriefing: {
      headline: "BureauOS Executive Dashboard V3",
      status: reports.summary.review_required || reports.summary.deployment_updates ? "attention" : "healthy",
      summary: "Using the existing Reports data while /api/dashboard/v2 is not available yet.",
      highlights: [
        `${reports.summary.completed_tasks} completed tasks in the current report window`,
        `${reports.summary.active_projects} active projects with recent activity`,
        `${reports.summary.completion_reports + reports.summary.qa_findings} weekly report files discovered`,
      ],
      risks: reports.summary.review_required
        ? [`${reports.summary.review_required} items require review`]
        : [],
      nextActions: reports.review_required.slice(0, 3).map((task) => task.title),
    },
    boardHealth: {
      metrics: [
        metric("Completed tasks", reports.summary.completed_tasks),
        metric("Review required", reports.summary.review_required),
        metric("Blocked tasks", reports.active_projects.reduce((sum, project) => sum + project.blocked_tasks, 0)),
        metric("Active projects", reports.summary.active_projects),
      ],
      statusCounts: reports.summary.status_counts,
    },
    portfolioHealth: {
      metrics: [
        metric("Active projects", reports.summary.active_projects),
        metric("Open project tasks", reports.active_projects.reduce((sum, project) => sum + project.active_tasks, 0)),
        metric("Projects blocked", reports.active_projects.filter((project) => project.blocked_tasks > 0).length),
      ],
      projects: reports.active_projects,
    },
    careerProgress: {
      status: "not configured",
      summary: "Career progress requires an opted-in career board or report source.",
      milestones: [],
    },
    engineeringMetrics: {
      metrics: [
        metric("Completed", reports.summary.completed_tasks),
        metric("Deployments", reports.summary.deployment_updates),
        metric("GitHub updates", reports.summary.github_updates),
        metric("QA findings", reports.summary.qa_findings),
      ],
      recentCompleted: reports.recent_completed,
      reviewRequired: reports.review_required,
      deploymentStatus: reports.deployment_status,
      githubActivity: reports.github_activity,
    },
    agentMetrics: {
      metrics: [],
      modelBreakdown: [],
      notes: ["Agent/session metrics will populate from /api/dashboard/v2 when the backend endpoint is enabled."],
    },
    financialMetrics: {
      metrics: [],
      notes: ["Financial/business metrics are not available from the legacy Reports API."],
    },
    weeklyReports: {
      completionReports: reports.completion_reports,
      qaFindings: reports.qa_findings,
      latestReports,
    },
    generatedReports: Object.values(reports.generated_reports?.latest ?? {}),
  };
}

function buildDashboardV2(data: DashboardV2Response, project: string, q: string): DashboardViewModel {
  const reports = reportsFromDashboard(data, project, q);
  const fallback = buildFallbackDashboard(reports);
  const briefing = data.executive_briefing ?? {};
  const board = data.board_health ?? {};
  const portfolio = data.portfolio_health ?? {};
  const engineering = data.engineering_metrics ?? {};
  const agent = data.agent_metrics ?? {};
  const providerHealth = data.provider_model_health ?? {};
  const providerTotals = providerHealth.totals ?? {};
  const financial = data.financial_metrics ?? {};
  const weekly = data.weekly_reports ?? {};
  const latestReports = asArray(weekly.latest_reports).length ? asArray(weekly.latest_reports) : asArray(weekly.latest);
  const topPriorities = asArray(briefing.top_priorities);
  const blockedTasks = asArray(briefing.blocked_tasks);
  const reviewRequiredTasks = asArray(briefing.review_required_tasks);
  const agentMetrics = asArray(agent.metrics).length
    ? asArray(agent.metrics)
    : [
        metric("Sessions", agent.sessions ?? providerTotals.sessions ?? 0),
        metric("API calls", agent.api_calls ?? providerTotals.api_calls ?? 0),
        metric("Tool calls", agent.tool_calls ?? providerTotals.tool_calls ?? 0),
        metric("Messages", agent.messages ?? providerTotals.messages ?? 0),
      ];
  const financialMetrics = asArray(financial.metrics).length
    ? asArray(financial.metrics)
    : [
        metric("AI cost est.", `$${Number(financial.ai_usage_cost_usd?.estimated ?? providerTotals.estimated_cost ?? 0).toFixed(2)}`),
        metric("AI cost actual", `$${Number(financial.ai_usage_cost_usd?.actual ?? providerTotals.actual_cost ?? 0).toFixed(2)}`),
        metric("Revenue", financial.revenue_usd == null ? "—" : `$${Number(financial.revenue_usd).toFixed(2)}`),
        metric("Burn", financial.burn_usd == null ? "—" : `$${Number(financial.burn_usd).toFixed(2)}`),
      ];

  return {
    ...fallback,
    source: "dashboard-v2",
    generatedAt: data.generated_at ?? reports.generated_at,
    executiveBriefing: {
      headline: briefing.headline || "BureauOS Executive Dashboard V3",
      status: briefing.status || (blockedTasks.length || reviewRequiredTasks.length ? "attention" : "healthy"),
      summary: briefing.summary || `${topPriorities.length} priorities, ${blockedTasks.length} blocked, ${reviewRequiredTasks.length} awaiting review.`,
      highlights: asArray(briefing.highlights).length
        ? asArray(briefing.highlights)
        : topPriorities.slice(0, 3).map((task) => task.title),
      risks: asArray(briefing.risks).length
        ? asArray(briefing.risks)
        : blockedTasks.slice(0, 3).map((task) => task.title),
      nextActions: asArray(briefing.next_actions).length
        ? asArray(briefing.next_actions)
        : reviewRequiredTasks.slice(0, 3).map((task) => task.title),
    },
    boardHealth: {
      metrics: [
        metric("Total tasks", board.total_tasks ?? Object.values(board.status_counts ?? {}).reduce((sum, count) => sum + count, 0)),
        metric("Active tasks", board.active_tasks ?? reports.active_projects.reduce((sum, p) => sum + p.active_tasks, 0)),
        metric("Blocked", board.blocked_tasks ?? reports.active_projects.reduce((sum, p) => sum + p.blocked_tasks, 0)),
        metric("Review", board.review_required ?? reports.summary.review_required),
      ],
      statusCounts: board.status_counts ?? reports.summary.status_counts,
    },
    portfolioHealth: {
      metrics: [
        metric("Active projects", portfolio.active_projects ?? reports.summary.active_projects),
        metric("Total projects", portfolio.total_projects ?? reports.summary.active_projects),
        metric("Blocked projects", reports.active_projects.filter((item) => item.blocked_tasks > 0).length),
      ],
      projects: reports.active_projects,
    },
    careerProgress: {
      status: data.career_progress?.status,
      summary: data.career_progress?.summary,
      milestones: asArray(data.career_progress?.milestones).length
        ? asArray(data.career_progress?.milestones)
        : asArray(data.career_progress?.items),
    },
    engineeringMetrics: {
      metrics: asArray(engineering.metrics).length
        ? asArray(engineering.metrics)
        : [
            metric("Completed", engineering.completed_tasks ?? reports.summary.completed_tasks),
            metric("Review required", engineering.review_required ?? reports.summary.review_required),
            metric("Blocked", engineering.blocked_tasks ?? board.blocked_tasks ?? 0),
            metric("Tests reported", engineering.tests_reported ?? 0),
          ],
      recentCompleted: reports.recent_completed,
      reviewRequired: reports.review_required,
      deploymentStatus: asArray(engineering.deployment_status).length ? asArray(engineering.deployment_status) : reports.deployment_status,
      githubActivity: asArray(engineering.github_activity).length ? asArray(engineering.github_activity) : reports.github_activity,
    },
    agentMetrics: {
      metrics: agentMetrics,
      modelBreakdown: asArray(agent.model_breakdown).length
        ? asArray(agent.model_breakdown)
        : asArray(providerHealth.models).slice(0, 8).map((item) => metric(item.model || "unknown model", item.sessions ?? 0, item.provider || undefined)),
      notes: asArray(agent.notes),
    },
    financialMetrics: {
      metrics: financialMetrics,
      notes: financialNotes(financial),
    },
    weeklyReports: {
      completionReports: asArray(weekly.completion_reports).length ? asArray(weekly.completion_reports) : reports.completion_reports,
      qaFindings: asArray(weekly.qa_findings).length ? asArray(weekly.qa_findings) : reports.qa_findings,
      latestReports: latestReports.length ? latestReports : fallback.weeklyReports.latestReports,
    },
    generatedReports: Object.values(data.generated_reports?.latest ?? reports.generated_reports?.latest ?? {}),
  };
}

function EmptyState({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center text-muted-foreground">
      <ClipboardList className="mb-3 h-8 w-8 opacity-40" />
      <p className="text-sm font-medium text-foreground">{label}</p>
      <p className="mt-1 max-w-md text-xs text-text-tertiary">{detail}</p>
    </div>
  );
}

function LoadingCard({ label }: { label: string }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-center gap-3 py-8 text-sm text-muted-foreground">
        <Spinner className="text-lg text-primary" />
        {label}
      </CardContent>
    </Card>
  );
}

function DashboardSection({
  title,
  icon,
  children,
  id,
}: {
  title: string;
  icon: ReactNode;
  children: ReactNode;
  id?: string;
}) {
  return (
    <Card id={id}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {icon}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function MetricGrid({ metrics, emptyLabel, emptyDetail }: { metrics: DashboardV2Metric[]; emptyLabel: string; emptyDetail: string }) {
  if (metrics.length === 0) return <EmptyState label={emptyLabel} detail={emptyDetail} />;
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map((item, index) => (
        <div key={`${item.label}-${index}`} className="rounded-lg border border-border/60 bg-card/70 p-3">
          <div className="text-xs text-muted-foreground">{item.label}</div>
          <div className="mt-1 text-2xl font-semibold text-foreground">{item.value ?? "—"}</div>
          {item.detail && <div className="mt-1 text-xs text-text-tertiary">{item.detail}</div>}
        </div>
      ))}
    </div>
  );
}

function TextList({ items, emptyLabel, emptyDetail }: { items: string[]; emptyLabel: string; emptyDetail: string }) {
  if (items.length === 0) return <EmptyState label={emptyLabel} detail={emptyDetail} />;
  return (
    <ul className="space-y-2 text-sm text-muted-foreground">
      {items.map((item, index) => (
        <li key={`${item}-${index}`} className="rounded border border-border/60 bg-card/60 px-3 py-2">{item}</li>
      ))}
    </ul>
  );
}

function TaskList({ tasks, emptyLabel }: { tasks: ReportsTaskSummary[]; emptyLabel: string }) {
  if (tasks.length === 0) {
    return <EmptyState label={emptyLabel} detail="No matching task history is available for the current filters." />;
  }
  return (
    <div className="divide-y divide-border/60">
      {tasks.map((task) => (
        <div key={task.id} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Link to={kanbanTaskHref(task.id)} className="truncate text-sm font-medium text-foreground hover:underline">
                {task.title}
              </Link>
              {task.status && <Badge className={statusTone(task.status)}>{task.status}</Badge>}
            </div>
            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{task.summary || "No summary provided."}</p>
            <p className="mt-1 font-mono text-xs text-text-tertiary">{task.id} · {task.project}</p>
          </div>
          <div className="shrink-0 text-left text-xs text-text-tertiary sm:text-right">
            {profileHref(task.assignee) ? (
              <Link to={profileHref(task.assignee)!} className="hover:text-foreground hover:underline">{task.assignee}</Link>
            ) : (
              <div>unassigned</div>
            )}
            <div>{formatDate(task.completed_at ?? task.created_at)}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ReportList({ reports, emptyLabel, emptyDetail }: { reports: ReportFileSummary[]; emptyLabel: string; emptyDetail?: string }) {
  if (reports.length === 0) {
    return <EmptyState label={emptyLabel} detail={emptyDetail || "Report files are read automatically from Hermes report directories."} />;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {reports.map((report) => (
        <Card key={report.id} className="bg-card/70">
          <CardContent className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <Link to={reportDetailHref(report)} className="truncate text-sm font-medium text-foreground hover:underline">{report.title}</Link>
                <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">{report.excerpt || "No preview available."}</p>
              </div>
              <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-text-tertiary">
              <Badge>{report.project}</Badge>
              <span>{formatDate(report.updated_at)}</span>
              <span className="truncate font-mono">{report.relative_path}</span>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

type ReportSection = {
  title: string;
  items: string[];
  body?: string;
};

type ReadableReport = {
  dateRange?: string;
  summary?: string;
  keyWins: string[];
  risks: string[];
  recommendations: string[];
  nextActions: string[];
  relatedItems: string[];
  otherSections: ReportSection[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function metadataPayload(report: GeneratedReportItem): Record<string, unknown> {
  const metadata = isRecord(report.metadata) ? report.metadata : {};
  return isRecord(metadata.raw_payload) ? metadata.raw_payload : metadata;
}

function formatReportValue(value: unknown): string[] {
  if (value === null || value === undefined) return [];
  if (typeof value === "string") return value.trim() ? [value.trim()] : [];
  if (typeof value === "number" || typeof value === "boolean") return [String(value)];
  if (Array.isArray(value)) return value.flatMap(formatReportValue);
  if (isRecord(value)) {
    const title = value.title ?? value.name ?? value.id ?? value.mission ?? value.task;
    const status = value.status ?? value.state;
    const owner = value.assignee ?? value.owner;
    const detail = value.summary ?? value.detail ?? value.description;
    const parts = [title, [status, owner].filter(Boolean).join(", "), detail]
      .map((item) => String(item || "").trim())
      .filter(Boolean);
    if (parts.length > 0) return [parts.join(" — ")];
    return [JSON.stringify(value)];
  }
  return [];
}

function firstReportValue(payload: Record<string, unknown>, aliases: string[]): unknown {
  for (const key of aliases) {
    const value = payload[key];
    if (value !== null && value !== undefined && value !== "" && !(Array.isArray(value) && value.length === 0)) {
      return value;
    }
  }
  return undefined;
}

function firstReportLines(payload: Record<string, unknown>, aliases: string[]): string[] {
  return formatReportValue(firstReportValue(payload, aliases));
}

function parseMarkdownSections(content?: string | null): ReportSection[] {
  if (!content) return [];
  const sections: ReportSection[] = [];
  let current: ReportSection | null = null;
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    const heading = line.match(/^##\s+(.+)$/);
    if (heading) {
      current = { title: heading[1], items: [] };
      sections.push(current);
      continue;
    }
    if (!current || !line || line.startsWith("# ")) continue;
    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) current.items.push(bullet[1]);
    else current.body = [current.body, line].filter(Boolean).join("\n");
  }
  return sections;
}

function buildReadableReport(report: GeneratedReportItem): ReadableReport {
  const payload = metadataPayload(report);
  const markdownSections = parseMarkdownSections(report.content);
  const sectionByTitle = new Map(markdownSections.map((section) => [section.title.toLowerCase(), section]));
  const markdownLines = (title: string) => {
    const section = sectionByTitle.get(title.toLowerCase());
    return section ? [...(section.body ? [section.body] : []), ...section.items] : [];
  };

  const summary = firstReportLines(payload, ["summary", "executive_summary", "overview", "brief", "abstract"])[0]
    ?? markdownLines("Executive summary")[0]
    ?? report.excerpt;
  const keyWins = firstReportLines(payload, ["key_wins", "wins", "highlights", "accomplishments", "successes"]);
  const risks = firstReportLines(payload, ["risks", "blockers", "risks_blockers", "risk_blockers", "issues", "concerns"]);
  const recommendations = firstReportLines(payload, ["recommendations", "recommendation", "suggestions", "guidance"]);
  const nextActions = firstReportLines(payload, ["next_actions", "actions", "action_items", "todos", "next_steps"]);
  const relatedItems = firstReportLines(payload, ["related_missions", "missions", "related_tasks", "tasks", "task_ids", "mission_ids", "linked_items"]);
  const knownTitles = new Set(["executive summary", "key wins", "risks / blockers", "recommendations", "next actions", "related missions / tasks"]);

  return {
    dateRange: formatReportValue(firstReportValue(payload, ["date_range", "range", "period", "reporting_period", "date"]))[0],
    summary,
    keyWins: keyWins.length ? keyWins : markdownLines("Key wins"),
    risks: risks.length ? risks : markdownLines("Risks / blockers"),
    recommendations: recommendations.length ? recommendations : markdownLines("Recommendations"),
    nextActions: nextActions.length ? nextActions : markdownLines("Next actions"),
    relatedItems: relatedItems.length ? relatedItems : markdownLines("Related missions / tasks"),
    otherSections: markdownSections.filter((section) => !knownTitles.has(section.title.toLowerCase())),
  };
}

function SectionList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-card/70 p-4">
      <h4 className="text-sm font-semibold text-foreground">{title}</h4>
      {items.length === 0 ? (
        <p className="mt-2 text-sm text-text-tertiary">{empty}</p>
      ) : (
        <ul className="mt-2 space-y-2 text-sm text-muted-foreground">
          {items.map((item, index) => <li key={`${title}-${index}`}>• {item}</li>)}
        </ul>
      )}
    </div>
  );
}

function GeneratedReportDetail({ entry }: { entry: GeneratedReportLatestEnvelope }) {
  if (!entry.report) {
    return <EmptyState label={`${entry.type_label} not generated`} detail={entry.error || "No report file is available yet."} />;
  }
  const report = entry.report;
  const readable = buildReadableReport(report);
  const rawPayload = metadataPayload(report);
  return (
    <div className="space-y-4">
      <Card className="bg-card/70">
        <CardContent className="p-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-xs uppercase tracking-wide text-text-tertiary">{entry.type_label}</p>
              <h2 className="mt-1 text-xl font-semibold text-foreground">{report.title || entry.type_label}</h2>
              <p className="mt-2 text-sm text-muted-foreground">{readable.summary || "No executive summary was provided."}</p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2 md:justify-end">
              <Badge className={statusTone(entry.status)}>{entry.status}</Badge>
              <Badge>{report.project || "default"}</Badge>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-3 text-xs text-text-tertiary">
            <span>{readable.dateRange || `Generated ${formatDate(report.generated_at)}`}</span>
            <span className="font-mono">{report.relative_path}</span>
          </div>
        </CardContent>
      </Card>

      <section className="grid gap-4 xl:grid-cols-2">
        <SectionList title="Key wins" items={readable.keyWins} empty="No key wins were listed." />
        <SectionList title="Risks / blockers" items={readable.risks} empty="No risks or blockers were listed." />
        <SectionList title="Recommendations" items={readable.recommendations} empty="No recommendations were listed." />
        <SectionList title="Next actions" items={readable.nextActions} empty="No next actions were listed." />
      </section>

      <SectionList title="Related missions / tasks" items={readable.relatedItems} empty="No related missions or tasks were linked." />
      {readable.otherSections.map((section) => (
        <SectionList key={section.title} title={section.title} items={[...(section.body ? [section.body] : []), ...section.items]} empty="No details." />
      ))}

      {Object.keys(rawPayload).length > 0 && (
        <details className="rounded-lg border border-border/60 bg-card/50 p-4 text-xs text-muted-foreground">
          <summary className="cursor-pointer font-medium text-foreground">Developer raw JSON</summary>
          <pre className="mt-3 max-h-96 overflow-auto rounded bg-background p-3 font-mono text-[11px] text-text-tertiary">
            {JSON.stringify(rawPayload, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}


function ReportFileDetail({ report }: { report: ReportFileSummary }) {
  return (
    <Card className="bg-card/70">
      <CardContent className="p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-wide text-text-tertiary">{report.kind || "report file"}</p>
            <h2 className="mt-1 text-xl font-semibold text-foreground">{report.title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{report.excerpt || "No report preview is available."}</p>
          </div>
          <Badge>{report.project || "default"}</Badge>
        </div>
        <div className="mt-4 flex flex-wrap gap-3 text-xs text-text-tertiary">
          <span>Updated {formatDate(report.updated_at)}</span>
          <span className="font-mono">{report.relative_path || report.path}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function GeneratedReportStatusList({ reports }: { reports: GeneratedReportLatestEnvelope[] }) {
  if (reports.length === 0) {
    return <EmptyState label="No generated report status" detail="Generated executive reports will appear after report crons write files." />;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {reports.map((entry) => {
        const readable = entry.report ? buildReadableReport(entry.report) : null;
        return (
        <Card key={entry.type} className="bg-card/70">
          <CardContent className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <Link to={generatedReportDetailHref(entry.type)} className="truncate text-sm font-medium text-foreground hover:underline">
                  {entry.report?.title || entry.type_label}
                </Link>
                <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">
                  {readable?.summary || entry.error || "Report has not been generated yet."}
                </p>
              </div>
              <Badge className={statusTone(entry.status)}>{entry.status}</Badge>
            </div>
            {readable && (
              <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                <div><span className="text-text-tertiary">Wins:</span> {readable.keyWins[0] || "—"}</div>
                <div><span className="text-text-tertiary">Risks:</span> {readable.risks[0] || "—"}</div>
                <div><span className="text-text-tertiary">Next:</span> {readable.nextActions[0] || "—"}</div>
              </div>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-text-tertiary">
              <span>{entry.report ? (readable?.dateRange || formatDate(entry.report.generated_at)) : "not generated"}</span>
              {entry.report?.relative_path && <span className="truncate font-mono">{entry.report.relative_path}</span>}
            </div>
          </CardContent>
        </Card>
      );})}
    </div>
  );
}

function ProjectList({ projects }: { projects: ReportsProjectSummary[] }) {
  if (projects.length === 0) {
    return <EmptyState label="No active projects" detail="Active triage, todo, ready, running, blocked, and review tasks will appear here." />;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {projects.map((project) => (
        <Card key={project.project} className="bg-card/70">
          <CardContent className="p-4">
            <div className="flex items-center justify-between gap-3">
              <Link to={boardHref(project.project)} className="truncate text-sm font-medium text-foreground hover:underline">{project.project}</Link>
              <Badge>{project.active_tasks} active</Badge>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded border border-border/60 p-2">
                <div className="text-base font-semibold text-foreground">{project.blocked_tasks}</div>
                <div className="text-text-tertiary">Blocked</div>
              </div>
              <div className="rounded border border-border/60 p-2">
                <div className="text-base font-semibold text-foreground">{project.review_required}</div>
                <div className="text-text-tertiary">Review</div>
              </div>
              <div className="rounded border border-border/60 p-2">
                <div className="text-base font-semibold text-foreground">{project.active_tasks}</div>
                <div className="text-text-tertiary">Open</div>
              </div>
            </div>
            <p className="mt-3 text-xs text-text-tertiary">Last activity {formatDate(project.latest_activity_at)}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function DeploymentList({ items }: { items: DeploymentStatusSummary[] }) {
  if (items.length === 0) {
    return <EmptyState label="No deployment status reports" detail="Files with deployment status lines will be summarized here." />;
  }
  return (
    <div className="divide-y divide-border/60">
      {items.map((item) => (
        <div key={`${item.path}-${item.updated_at}`} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-foreground">{item.title}</span>
              <Badge className={statusTone(item.status)}>{item.status}</Badge>
            </div>
            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{item.excerpt}</p>
          </div>
          <div className="shrink-0 text-xs text-text-tertiary sm:text-right">
            <div>{item.project}</div>
            <div>{formatDate(item.updated_at)}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function ReportsPage() {
  const { type: reportType } = useParams<{ type?: string }>();
  const [searchParams] = useSearchParams();
  const reportId = searchParams.get("report");
  const { setAfterTitle, setEnd } = usePageHeader();
  const [dashboard, setDashboard] = useState<DashboardViewModel | null>(null);
  const [selectedReport, setSelectedReport] = useState<GeneratedReportLatestEnvelope | null>(null);
  const [project, setProject] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSelectedReport(null);
      try {
        const data = await api.getDashboardV2({ days: 7, project, q: query });
        setDashboard(buildDashboardV2(data, project, query));
      } catch (err) {
        if (!isMissingDashboardEndpoint(err)) throw err;
        const reports = await api.getReports({ project, q: query, limit: 50 });
        setDashboard(buildFallbackDashboard(reports));
      }
      if (reportType) {
        const report = await api.getLatestGeneratedReport(reportType);
        setSelectedReport(report);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setDashboard((current) => current ?? buildFallbackDashboard(createEmptyReports(project, query)));
    } finally {
      setLoading(false);
    }
  }, [project, query, reportType]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    setAfterTitle(
      <span className="hidden font-mondwest text-xs normal-case text-muted-foreground sm:inline">
        BureauOS Executive Dashboard V3
      </span>,
    );
    setEnd(
      <Button outlined size="sm" onClick={load} disabled={loading}>
        <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        Refresh
      </Button>,
    );
    return () => {
      setAfterTitle(null);
      setEnd(null);
    };
  }, [load, loading, setAfterTitle, setEnd]);

  const statItems = useMemo(() => {
    const summary = dashboard?.reports.summary;
    return [
      { label: "Completed tasks", value: String(summary?.completed_tasks ?? 0), icon: <CheckCircle2 className="h-4 w-4" /> },
      { label: "Review required", value: String(summary?.review_required ?? 0), icon: <AlertTriangle className="h-4 w-4" /> },
      { label: "Active projects", value: String(summary?.active_projects ?? 0), icon: <ClipboardList className="h-4 w-4" /> },
      { label: "Weekly report files", value: String((summary?.completion_reports ?? 0) + (summary?.qa_findings ?? 0)), icon: <FileText className="h-4 w-4" /> },
      { label: "Deployments", value: String(summary?.deployment_updates ?? 0), icon: <Server className="h-4 w-4" /> },
      { label: "GitHub updates", value: String(summary?.github_updates ?? 0), icon: <GitBranch className="h-4 w-4" /> },
    ];
  }, [dashboard]);


  const selectedFileReport = useMemo(() => {
    if (!dashboard || !reportId) return null;
    return [
      ...dashboard.weeklyReports.completionReports,
      ...dashboard.weeklyReports.qaFindings,
      ...dashboard.weeklyReports.latestReports,
      ...dashboard.engineeringMetrics.githubActivity,
    ].find((report) => report.id === reportId) ?? null;
  }, [dashboard, reportId]);

  const isEmpty = dashboard &&
    dashboard.reports.recent_completed.length === 0 &&
    dashboard.reports.review_required.length === 0 &&
    dashboard.reports.active_projects.length === 0 &&
    dashboard.weeklyReports.completionReports.length === 0 &&
    dashboard.weeklyReports.qaFindings.length === 0 &&
    dashboard.generatedReports.length === 0 &&
    dashboard.engineeringMetrics.deploymentStatus.length === 0 &&
    dashboard.engineeringMetrics.githubActivity.length === 0 &&
    dashboard.agentMetrics.metrics.length === 0 &&
    dashboard.financialMetrics.metrics.length === 0;

  return (
    <div className="flex flex-col gap-6">
      <PluginSlot name="reports:top" />

      {dashboard && (
        <DashboardSection id="command-brief" title="Command Brief" icon={<Activity className="h-5 w-5 text-primary" />}>
          <div className="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
            <div className="rounded-xl border border-primary/20 bg-primary/5 p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.2em] text-primary">Mission control</p>
                  <h2 className="mt-2 text-2xl font-semibold text-foreground">{dashboard.executiveBriefing.headline}</h2>
                </div>
                <Badge className={statusTone(dashboard.executiveBriefing.status)}>{dashboard.executiveBriefing.status}</Badge>
              </div>
              <p className="mt-4 text-sm leading-6 text-muted-foreground">{dashboard.executiveBriefing.summary}</p>
            </div>
            <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-1">
              <div>
                <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text-tertiary">Yesterday summary</h3>
                <TextList items={dashboard.executiveBriefing.highlights} emptyLabel="No highlights" emptyDetail="Completed outcomes will appear when dashboard briefing data is available." />
              </div>
              <div>
                <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text-tertiary">Risks and blockers</h3>
                <TextList items={dashboard.executiveBriefing.risks} emptyLabel="No risks flagged" emptyDetail="Blocked missions and report risks will appear here." />
              </div>
              <div>
                <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text-tertiary">Today's priorities and recommendations</h3>
                <TextList items={dashboard.executiveBriefing.nextActions} emptyLabel="No next actions" emptyDetail="Recommended executive follow-ups will appear here." />
              </div>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <Link to={EXECUTIVE_AREA_HREFS.careerDevelopment} className="rounded-lg border border-border/60 bg-card/70 p-3 text-sm font-medium text-foreground hover:bg-secondary/60">Career Development</Link>
            <Link to={EXECUTIVE_AREA_HREFS.bureauos} className="rounded-lg border border-border/60 bg-card/70 p-3 text-sm font-medium text-foreground hover:bg-secondary/60">BureauOS</Link>
            <Link to={EXECUTIVE_AREA_HREFS.engineeringBrand} className="rounded-lg border border-border/60 bg-card/70 p-3 text-sm font-medium text-foreground hover:bg-secondary/60">Engineering Brand</Link>
            <Link to={EXECUTIVE_AREA_HREFS.artistManagement} className="rounded-lg border border-border/60 bg-card/70 p-3 text-sm font-medium text-foreground hover:bg-secondary/60">Artist Management</Link>
            <Link to={EXECUTIVE_AREA_HREFS.venturePortfolio} className="rounded-lg border border-border/60 bg-card/70 p-3 text-sm font-medium text-foreground hover:bg-secondary/60">Venture Portfolio</Link>
            <Link to={EXECUTIVE_AREA_HREFS.hermesOperations} className="rounded-lg border border-border/60 bg-card/70 p-3 text-sm font-medium text-foreground hover:bg-secondary/60">Hermes Operations</Link>
          </div>
        </DashboardSection>
      )}

      <Card>
        <CardContent className="p-4">
          <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              Project filter
              <input
                value={project}
                onChange={(event) => setProject(event.target.value)}
                placeholder="Any project"
                className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              Search reports and tasks
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-tertiary" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="review, deployment, GitHub…"
                  className="h-10 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
            </label>
            <div className="flex items-end">
              <Button className="w-full md:w-auto" onClick={load} disabled={loading}>
                Apply
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {loading && !dashboard && <LoadingCard label="Loading BureauOS Executive Dashboard V3…" />}

      {error && (
        <Card>
          <CardContent className="py-6 text-center text-sm text-destructive">
            Dashboard data failed to load: {error}
          </CardContent>
        </Card>
      )}

      {reportType && selectedReport && (
        <DashboardSection title="Report Detail" icon={<FileText className="h-5 w-5 text-primary" />}>
          <div className="mb-4">
            <Link
              to="/reports"
              className="inline-flex h-9 items-center rounded-md border border-border px-3 text-sm text-foreground hover:bg-secondary/60"
            >
              Back to reports
            </Link>
          </div>
          <GeneratedReportDetail entry={selectedReport} />
        </DashboardSection>
      )}

      {!reportType && selectedFileReport && (
        <DashboardSection title="Report Detail" icon={<FileText className="h-5 w-5 text-primary" />}>
          <div className="mb-4">
            <Link
              to="/reports"
              className="inline-flex h-9 items-center rounded-md border border-border px-3 text-sm text-foreground hover:bg-secondary/60"
            >
              Back to reports
            </Link>
          </div>
          <ReportFileDetail report={selectedFileReport} />
        </DashboardSection>
      )}

      {dashboard && (
        <>
          {isEmpty && (
            <Card>
              <CardContent>
                <EmptyState
                  label="No dashboard data matched"
                  detail="Try removing filters, completing kanban tasks, or adding markdown report files under Hermes reports directories."
                />
              </CardContent>
            </Card>
          )}

          <section className="grid gap-6 xl:grid-cols-2">
            <DashboardSection id={EXECUTIVE_AREA_TARGETS.bureauos} title="BureauOS" icon={<ClipboardList className="h-5 w-5 text-muted-foreground" />}>
              <MetricGrid metrics={dashboard.boardHealth.metrics} emptyLabel="No board metrics" emptyDetail="Kanban status counts will populate this card." />
              <div className="mt-4 flex flex-wrap gap-2">
                {Object.entries(dashboard.boardHealth.statusCounts).length === 0 ? (
                  <p className="text-xs text-text-tertiary">No status-count breakdown available.</p>
                ) : Object.entries(dashboard.boardHealth.statusCounts).map(([status, count]) => (
                  <Badge key={status} className={statusTone(status)}>{status}: {count}</Badge>
                ))}
              </div>
            </DashboardSection>

            <DashboardSection id={EXECUTIVE_AREA_TARGETS.venturePortfolio} title="Venture Portfolio" icon={<BriefcaseBusiness className="h-5 w-5 text-muted-foreground" />}>
              <MetricGrid metrics={dashboard.portfolioHealth.metrics} emptyLabel="No portfolio metrics" emptyDetail="Portfolio metadata is optional and may not be configured yet." />
              <div className="mt-4">
                <ProjectList projects={dashboard.portfolioHealth.projects} />
              </div>
            </DashboardSection>
          </section>

          <section className="grid gap-6 xl:grid-cols-2">
            <DashboardSection id={EXECUTIVE_AREA_TARGETS.careerDevelopment} title="Career Development" icon={<GraduationCap className="h-5 w-5 text-muted-foreground" />}>
              <div className="mb-4 rounded-lg border border-border/60 bg-card/70 p-4">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-foreground">{dashboard.careerProgress.status || "Not configured"}</span>
                  <Badge className={statusTone(dashboard.careerProgress.status || "not configured")}>{dashboard.careerProgress.status || "placeholder"}</Badge>
                </div>
                <p className="mt-2 text-sm text-muted-foreground">
                  {dashboard.careerProgress.summary || "No opted-in career progress source is configured."}
                </p>
              </div>
              <MetricGrid metrics={dashboard.careerProgress.milestones} emptyLabel="No career milestones" emptyDetail="Connect a career board/report source to populate progress milestones." />
            </DashboardSection>

            <DashboardSection id={EXECUTIVE_AREA_TARGETS.engineeringBrand} title="Engineering Brand" icon={<LineChart className="h-5 w-5 text-muted-foreground" />}>
              <MetricGrid metrics={dashboard.engineeringMetrics.metrics} emptyLabel="No engineering metrics" emptyDetail="Engineering metrics will populate from task and report activity." />
            </DashboardSection>
          </section>

          <section className="grid gap-6 xl:grid-cols-2">
            <DashboardSection id={EXECUTIVE_AREA_TARGETS.hermesOperations} title="Hermes Operations" icon={<Bot className="h-5 w-5 text-muted-foreground" />}>
              <div className="mb-4 rounded-lg border border-border/60 bg-card/70 p-4">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-base font-semibold text-foreground">System activity and platform metrics</h3>
                    <p className="mt-1 text-sm text-muted-foreground">Raw task/session counters are scoped here so the homepage remains mission-centric.</p>
                  </div>
                  <Badge className={statusTone(dashboard.executiveBriefing.status)}>
                    {dashboard.source === "dashboard-v2" ? "Dashboard v2 API" : "Reports compatibility mode"}
                  </Badge>
                </div>
                <Stats items={statItems} />
              </div>
              <MetricGrid metrics={dashboard.agentMetrics.metrics} emptyLabel="No agent metrics" emptyDetail="Session/model analytics are unavailable for the current filters." />
              <div className="mt-4">
                <MetricGrid metrics={dashboard.agentMetrics.modelBreakdown} emptyLabel="No model breakdown" emptyDetail="Model usage will appear when analytics data is available." />
              </div>
              {dashboard.agentMetrics.notes.length > 0 && <div className="mt-4"><TextList items={dashboard.agentMetrics.notes} emptyLabel="No agent notes" emptyDetail="" /></div>}
            </DashboardSection>

            <DashboardSection id={EXECUTIVE_AREA_TARGETS.artistManagement} title="Artist Management" icon={<DollarSign className="h-5 w-5 text-muted-foreground" />}>
              <EmptyState label="No artist management source" detail="Artist roster, campaign, release, and blocker data is not configured yet; connect a report source to populate this mission area." />
            </DashboardSection>
          </section>

          <section className="grid gap-6 xl:grid-cols-2">
            <DashboardSection title="Recent completed work" icon={<CheckCircle2 className="h-5 w-5 text-emerald-500" />}>
              <TaskList tasks={dashboard.engineeringMetrics.recentCompleted} emptyLabel="No completed tasks" />
            </DashboardSection>

            <DashboardSection title="Review queue" icon={<AlertTriangle className="h-5 w-5 text-amber-500" />}>
              <TaskList tasks={dashboard.engineeringMetrics.reviewRequired} emptyLabel="No review queue" />
            </DashboardSection>
          </section>

          <section className="grid gap-6 xl:grid-cols-2">
            <DashboardSection title="Deployment status" icon={<Server className="h-5 w-5 text-muted-foreground" />}>
              <DeploymentList items={dashboard.engineeringMetrics.deploymentStatus} />
            </DashboardSection>

            <DashboardSection title="GitHub activity" icon={<GitBranch className="h-5 w-5 text-muted-foreground" />}>
              <ReportList reports={dashboard.engineeringMetrics.githubActivity} emptyLabel="No GitHub activity reports" />
            </DashboardSection>
          </section>

          <DashboardSection title="Reports" icon={<FileText className="h-5 w-5 text-muted-foreground" />}>
            <GeneratedReportStatusList reports={dashboard.generatedReports} />
          </DashboardSection>

          <DashboardSection title="Report Library" icon={<CalendarDays className="h-5 w-5 text-muted-foreground" />}>
            <section className="grid gap-6 xl:grid-cols-2">
              <div>
                <h3 className="mb-3 text-sm font-medium text-foreground">Completion reports</h3>
                <ReportList reports={dashboard.weeklyReports.completionReports} emptyLabel="No completion report files" />
              </div>
              <div>
                <h3 className="mb-3 text-sm font-medium text-foreground">QA findings</h3>
                <ReportList reports={dashboard.weeklyReports.qaFindings} emptyLabel="No QA findings" />
              </div>
            </section>
            <div className="mt-6">
              <h3 className="mb-3 text-sm font-medium text-foreground">Latest report links</h3>
              <ReportList reports={dashboard.weeklyReports.latestReports} emptyLabel="No latest reports" emptyDetail="Latest report links will appear when report files are discovered." />
            </div>
          </DashboardSection>

          <p className="flex items-center gap-1 text-xs text-text-tertiary">
            <ExternalLink className="h-3.5 w-3.5" /> Generated {formatDate(dashboard.generatedAt)} from {dashboard.source === "dashboard-v2" ? "/api/dashboard/v2" : "the existing /api/reports compatibility path"}.
          </p>
        </>
      )}
      <PluginSlot name="reports:bottom" />
    </div>
  );
}
