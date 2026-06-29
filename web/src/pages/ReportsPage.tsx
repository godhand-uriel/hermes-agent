import { useCallback, useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  ClipboardList,
  FileText,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  DashboardV2Metric,
  DashboardFinanceTrend,
  DashboardOperatingNote,
  DashboardV2BureauOSApplication,
  DashboardV2PipelineStage,
  DashboardV2Response,
  DashboardV2WatchdogStatus,
  DeploymentStatusSummary,
  FinanceSyncStatus,
  GeneratedReportItem,
  GeneratedReportLatestEnvelope,
  ReportFileSummary,
  ReportsProjectSummary,
  ReportsResponse,
  ReportsTaskSummary,
} from "@/lib/api";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { usePageHeader } from "@/contexts/usePageHeader";
import { PluginSlot } from "@/plugins";

type DataSource = "dashboard-v2" | "reports-fallback";

interface OperatingNoteViewModel {
  status?: string | null;
  summary?: string | null;
  phase?: string | null;
  priorities: string[];
  blockers: string[];
  risks: string[];
  nextActions: string[];
  kpis: string[];
  milestones: DashboardV2Metric[];
}

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
  notificationWatchdog: DashboardV2WatchdogStatus;
  portfolioHealth: {
    metrics: DashboardV2Metric[];
    projects: ReportsProjectSummary[];
  };
  bureauosApplications: DashboardV2BureauOSApplication[];
  venturePipeline: DashboardV2PipelineStage[];
  careerProgress: OperatingNoteViewModel;
  artistManagement: OperatingNoteViewModel;
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
    trends: Record<string, DashboardFinanceTrend>;
    sync: FinanceSyncStatus | null;
    source: { type?: string | null; configured?: boolean | null; path?: string | null; model?: string | null } | null;
  };
  empireHealth: {
    score?: number | null;
    components: Record<string, number>;
    weights: Record<string, number>;
  };
  weeklyReports: {
    completionReports: ReportFileSummary[];
    qaFindings: ReportFileSummary[];
    latestReports: ReportFileSummary[];
  };
  generatedReports: GeneratedReportLatestEnvelope[];
  empireHealthScore?: number | null;
  knowledgeVault?: DashboardV2Response["knowledge_vault"];
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

function formatRelativeTime(value?: number | null): string {
  if (!value) return "Never";
  const seconds = Math.max(0, Math.floor((Date.now() - value * 1000) / 1000));
  if (seconds < 60) return `${seconds || 1} seconds ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function formatDuration(value?: number | null): string {
  if (value == null) return "—";
  return `${Number(value).toFixed(1)} seconds`;
}

function syncHealthLabel(value?: string | null): "Healthy" | "Warning" | "Error" {
  const normalized = (value || "").toLowerCase();
  if (normalized === "healthy") return "Healthy";
  if (normalized === "error" || normalized === "failed") return "Error";
  return "Warning";
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

function operatingNoteFromApi(note?: DashboardOperatingNote | null): OperatingNoteViewModel {
  return {
    status: note?.status,
    summary: note?.summary,
    phase: note?.phase,
    priorities: asArray(note?.priorities),
    blockers: asArray(note?.blockers),
    risks: asArray(note?.risks),
    nextActions: asArray(note?.next_actions),
    kpis: asArray(note?.kpis),
    milestones: asArray(note?.milestones).length ? asArray(note?.milestones) : asArray(note?.items),
  };
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
    rank: item.rank ?? null,
    stage: item.stage ?? null,
    confidence: item.confidence ?? null,
    revenue_usd: item.revenue_usd ?? null,
    next_milestone: item.next_milestone ?? item.recommendation ?? null,
    score: item.score ?? null,
    status: item.status ?? null,
    recommendation: item.recommendation ?? item.next_milestone ?? null,
    summary: item.summary ?? null,
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
      headline: "Hermes OS Executive Command Center",
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
    notificationWatchdog: {
      status: "unconfigured",
      coverage_percent: null,
      last_audit_at: null,
      active_issues: 0,
      remediation_count: 0,
      alerts: [],
    },
    portfolioHealth: {
      metrics: [
        metric("Registered ventures", reports.summary.active_projects),
        metric("Open venture tasks", reports.active_projects.reduce((sum, project) => sum + project.active_tasks, 0)),
        metric("Ventures blocked", reports.active_projects.filter((project) => project.blocked_tasks > 0).length),
      ],
      projects: reports.active_projects,
    },
    bureauosApplications: [],
    venturePipeline: [],
    careerProgress: {
      status: "source unavailable",
      summary: "Career source layer unavailable from /api/dashboard/v2.",
      phase: null,
      priorities: [],
      blockers: [],
      risks: [],
      nextActions: [],
      kpis: [],
      milestones: [],
    },
    artistManagement: {
      status: "source unavailable",
      summary: "Artist CRM source layer unavailable from /api/dashboard/v2.",
      phase: null,
      priorities: [],
      blockers: [],
      risks: [],
      nextActions: [],
      kpis: [],
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
      trends: {},
      sync: null,
      source: null,
    },
    empireHealth: {
      score: null,
      components: {},
      weights: {},
    },
    weeklyReports: {
      completionReports: reports.completion_reports,
      qaFindings: reports.qa_findings,
      latestReports,
    },
    generatedReports: Object.values(reports.generated_reports?.latest ?? {}),
    empireHealthScore: null,
    knowledgeVault: null,
  };
}

function buildDashboardV2(data: DashboardV2Response, project: string, q: string): DashboardViewModel {
  const reports = reportsFromDashboard(data, project, q);
  const fallback = buildFallbackDashboard(reports);
  const briefing = data.executive_briefing ?? {};
  const board = data.board_health ?? {};
  const watchdog = data.notification_watchdog ?? {};
  const portfolio = data.portfolio_health ?? {};
  const engineering = data.engineering_metrics ?? {};
  const agent = data.agent_metrics ?? {};
  const providerHealth = data.provider_model_health ?? {};
  const providerTotals = providerHealth.totals ?? {};
  const financial = data.financial_metrics ?? {};
  const engineeringBrand = data.engineering_brand ?? {};
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
  const financeCommandCenter = financial.finance_command_center as { widgets?: DashboardV2Metric[] | null } | undefined;
  const sourceFinanceWidgets = asArray(financial.metrics).length
    ? asArray(financial.metrics)
    : asArray(financial.widgets).length
    ? asArray(financial.widgets)
    : asArray(financeCommandCenter?.widgets);
  const financialMetrics = sourceFinanceWidgets.length
    ? sourceFinanceWidgets
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
      headline: briefing.headline || "Hermes OS Executive Command Center",
      status: briefing.status || (blockedTasks.length || reviewRequiredTasks.length ? "attention" : "healthy"),
      summary: briefing.summary || `${topPriorities.length} priorities, ${blockedTasks.length} blocked, ${reviewRequiredTasks.length} pending review.`,
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
    notificationWatchdog: {
      ...watchdog,
      alerts: asArray(watchdog.alerts),
    },
    portfolioHealth: {
      metrics: [
        metric("Registered ventures", portfolio.total_projects ?? reports.summary.active_projects),
        metric("Open venture tasks", reports.active_projects.reduce((sum, item) => sum + item.active_tasks, 0)),
        metric("Ventures blocked", reports.active_projects.filter((item) => item.blocked_tasks > 0).length),
      ],
      projects: reports.active_projects,
    },
    bureauosApplications: asArray(data.bureauos_application_registry?.applications).length
      ? asArray(data.bureauos_application_registry?.applications)
      : asArray(data.bureauos_applications),
    venturePipeline: asArray(data.venture_pipeline?.stages),
    careerProgress: operatingNoteFromApi(data.career_progress),
    artistManagement: operatingNoteFromApi(data.artist_management),
    engineeringMetrics: {
      metrics: asArray(engineeringBrand.metrics).length
        ? asArray(engineeringBrand.metrics)
        : asArray(engineering.metrics).length
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
      trends: financial.trends ?? {},
      sync: ((financeCommandCenter as { sync?: FinanceSyncStatus | null } | undefined)?.sync ?? null) as FinanceSyncStatus | null,
      source: (financial.source ?? ((financeCommandCenter as { source?: DashboardViewModel["financialMetrics"]["source"] } | undefined)?.source ?? null)) as DashboardViewModel["financialMetrics"]["source"],
    },
    empireHealth: {
      score: data.empire_health?.score ?? null,
      components: data.empire_health?.components ?? {},
      weights: data.empire_health?.weights ?? {},
    },
    weeklyReports: {
      completionReports: asArray(weekly.completion_reports).length ? asArray(weekly.completion_reports) : reports.completion_reports,
      qaFindings: asArray(weekly.qa_findings).length ? asArray(weekly.qa_findings) : reports.qa_findings,
      latestReports: latestReports.length ? latestReports : fallback.weeklyReports.latestReports,
    },
    generatedReports: Object.values(data.generated_reports?.latest ?? reports.generated_reports?.latest ?? {}),
    empireHealthScore: data.empire_health?.score ?? null,
    knowledgeVault: data.knowledge_vault ?? null,
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

function OperatingNoteCard({ note, emptyDetail }: { note: OperatingNoteViewModel; emptyDetail: string }) {
  const hasContent = Boolean(
    note.summary
      || note.phase
      || note.priorities.length
      || note.blockers.length
      || note.risks.length
      || note.nextActions.length
      || note.kpis.length,
  );
  if (!hasContent) return <EmptyState label="No operating-note source" detail={emptyDetail} />;

  const groups = [
    { title: "Priorities", items: note.priorities },
    { title: "Blockers", items: note.blockers },
    { title: "Risks", items: note.risks },
    { title: "Next actions", items: note.nextActions },
    { title: "KPIs", items: note.kpis },
  ];

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border/60 bg-card/70 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-foreground">{note.phase || note.status || "Operating note"}</span>
          <Badge className={statusTone(note.status || "available")}>{note.status || "available"}</Badge>
        </div>
        {note.summary && <p className="mt-2 text-sm text-muted-foreground">{note.summary}</p>}
      </div>
      <MetricGrid metrics={note.milestones} emptyLabel="No operating metrics" emptyDetail="Phase, priorities, blockers, risks, next actions, and KPIs will appear when present in the note." />
      <div className="grid gap-3 md:grid-cols-2">
        {groups.map((group) => (
          <div key={group.title} className="rounded-lg border border-border/60 bg-card/70 p-3">
            <h3 className="text-sm font-medium text-foreground">{group.title}</h3>
            {group.items.length ? (
              <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                {group.items.slice(0, 5).map((item, index) => <li key={`${group.title}-${index}`}>• {item}</li>)}
              </ul>
            ) : (
              <p className="mt-2 text-xs text-text-tertiary">No {group.title.toLowerCase()} recorded.</p>
            )}
          </div>
        ))}
      </div>
    </div>
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
    return <EmptyState label="No registered ventures" detail="No ventures configured." />;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {projects.map((project) => (
        <Card key={project.project} className="bg-card/70">
          <CardContent className="p-4">
            <div className="flex items-center justify-between gap-3">
              <Link to={boardHref(project.project)} className="truncate text-sm font-medium text-foreground hover:underline">{project.project}</Link>
              <div className="flex shrink-0 items-center gap-2">
                {project.rank != null && <Badge>#{project.rank}</Badge>}
                <Badge>{project.active_tasks} active</Badge>
              </div>
            </div>
            {(project.summary || project.recommendation || project.status) && (
              <div className="mt-3 rounded border border-border/60 bg-background/50 p-3 text-xs text-muted-foreground">
                {project.status && <Badge className={statusTone(project.status)}>{project.status}</Badge>}
                {project.summary && <p className="mt-2">{project.summary}</p>}
                {project.recommendation && <p className="mt-2 font-medium text-foreground">Next: {project.recommendation}</p>}
              </div>
            )}
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

const LEGACY_REPORTS_ROUTE_DEFINITIONS = [
  EXECUTIVE_AREA_TARGETS,
  EXECUTIVE_AREA_HREFS,
  DashboardSection,
  TaskList,
  ReportList,
  GeneratedReportDetail,
  ReportFileDetail,
  GeneratedReportStatusList,
  ProjectList,
  DeploymentList,
  TextList,
  OperatingNoteCard,
];
void LEGACY_REPORTS_ROUTE_DEFINITIONS;

function SourceStamp({ source, updated }: { source: string; updated?: number | null }) {
  return (
    <p className="mt-3 border-t border-white/10 pt-2 text-[9px] uppercase tracking-[0.18em] text-slate-500">
      Source: {source} · Updated {formatDate(updated)}
    </p>
  );
}

function ExecutivePanel({
  eyebrow,
  title,
  source,
  updated,
  children,
  className = "",
}: {
  eyebrow: string;
  title: string;
  source: string;
  updated?: number | null;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`group overflow-hidden rounded-2xl border border-white/10 bg-[#07101d]/92 p-3 shadow-xl shadow-black/30 ring-1 ring-white/[0.03] ${className}`}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[9px] font-semibold uppercase tracking-[0.24em] text-cyan-300/80">{eyebrow}</p>
          <h3 className="mt-1 truncate text-sm font-semibold text-white">{title}</h3>
        </div>
        <span className="shrink-0 rounded-full border border-white/10 bg-white/[0.04] px-2 py-1 text-[9px] uppercase tracking-[0.14em] text-slate-400">Live</span>
      </div>
      {children}
      <SourceStamp source={source} updated={updated} />
    </div>
  );
}

function clampPercent(value?: number | string | null): number | null {
  if (value == null || value === "") return null;
  const numeric = typeof value === "number" ? value : Number(String(value).replace(/[^0-9.-]/g, ""));
  if (!Number.isFinite(numeric)) return null;
  return Math.max(0, Math.min(100, numeric));
}

function toneFromStatus(status?: string | null): "good" | "warn" | "bad" | "muted" {
  const value = (status || "").toLowerCase();
  if (["healthy", "available", "on track", "done", "stable", "active", "data available"].some((needle) => value.includes(needle))) return "good";
  if (["blocked", "failed", "at risk", "outage"].some((needle) => value.includes(needle))) return "bad";
  if (["degraded", "review", "attention", "watch", "warning"].some((needle) => value.includes(needle))) return "warn";
  return "muted";
}

function toneClasses(tone: "good" | "warn" | "bad" | "muted") {
  switch (tone) {
    case "good": return { text: "text-emerald-300", bg: "bg-emerald-400", border: "border-emerald-400/30", soft: "bg-emerald-400/10", fill: "#34d399" };
    case "warn": return { text: "text-amber-300", bg: "bg-amber-400", border: "border-amber-400/30", soft: "bg-amber-400/10", fill: "#fbbf24" };
    case "bad": return { text: "text-rose-300", bg: "bg-rose-400", border: "border-rose-400/30", soft: "bg-rose-400/10", fill: "#fb7185" };
    default: return { text: "text-slate-400", bg: "bg-slate-500", border: "border-white/10", soft: "bg-white/[0.04]", fill: "#64748b" };
  }
}

function SignalDot({ tone }: { tone: "good" | "warn" | "bad" | "muted" }) {
  const cls = toneClasses(tone);
  return <span className={`h-2 w-2 shrink-0 rounded-full ${cls.bg} shadow-[0_0_16px_currentColor] ${cls.text}`} />;
}

function Sparkline({ tone = "good", values = [16, 32, 24, 46, 40, 58, 52] }: { tone?: "good" | "warn" | "bad" | "muted"; values?: number[] }) {
  const color = toneClasses(tone).fill;
  const max = Math.max(...values, 1);
  const points = values.map((value, index) => `${(index / Math.max(values.length - 1, 1)) * 100},${28 - (value / max) * 24}`).join(" ");
  return (
    <svg viewBox="0 0 100 32" className="h-8 w-full overflow-visible" aria-hidden="true">
      <polyline points={points} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points={`${points} 100,32 0,32`} fill={color} opacity="0.08" />
    </svg>
  );
}

function Gauge({ value, label, tone = "good", fallback = "No Metrics Yet" }: { value: number | null; label: string; tone?: "good" | "warn" | "bad" | "muted"; fallback?: string }) {
  const percent = value == null ? 0 : Math.max(0, Math.min(100, value));
  const color = toneClasses(tone).fill;
  const style = { "--gauge": `${percent}%`, "--gauge-color": color } as CSSProperties;
  return (
    <div className="flex items-center gap-3">
      <div className="grid h-20 w-20 shrink-0 place-items-center rounded-full bg-[conic-gradient(var(--gauge-color)_var(--gauge),rgba(255,255,255,.08)_0)] p-2" style={style}>
        <div className="grid h-full w-full place-items-center rounded-full bg-[#07101d] text-center">
          <div>
            <div className="text-xl font-semibold text-white">{value == null ? "—" : `${Math.round(percent)}%`}</div>
            <div className="text-[8px] uppercase tracking-[0.18em] text-slate-500">Score</div>
          </div>
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs uppercase tracking-[0.18em] text-slate-400">{label}</p>
        <Sparkline tone={tone} />
        <p className="text-[10px] text-slate-500">{value == null ? fallback : "30-day trend from source signals"}</p>
      </div>
    </div>
  );
}

function ProgressBar({ label, value, detail, tone = "good" }: { label: string; value: number | null; detail?: string; tone?: "good" | "warn" | "bad" | "muted" }) {
  const pct = value ?? 0;
  const cls = toneClasses(tone);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2 text-[11px]">
        <span className="truncate text-slate-300">{label}</span>
        <span className={cls.text}>{value == null ? "0%" : `${Math.round(pct)}%`}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
        <div className={`h-full rounded-full ${cls.bg}`} style={{ width: `${Math.max(3, Math.min(100, pct))}%` }} />
      </div>
      {detail && <p className="text-[10px] text-slate-500">{detail}</p>}
    </div>
  );
}

function MetricTile({ label, value, detail, tone = "muted", compact = false }: { label: string; value: string | number; detail?: string; tone?: "good" | "warn" | "bad" | "muted"; compact?: boolean }) {
  const cls = toneClasses(tone);
  return (
    <div className={`rounded-lg border ${cls.border} ${cls.soft} ${compact ? "px-2 py-1.5" : "p-2.5"}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-[9px] uppercase tracking-[0.14em] text-slate-500">{label}</p>
        <SignalDot tone={tone} />
      </div>
      <p className={`${compact ? "mt-1 text-sm" : "mt-1.5 text-lg"} truncate font-semibold text-white`}>{value}</p>
      {detail && <p className="mt-1 line-clamp-1 text-[10px] text-slate-400">{detail}</p>}
    </div>
  );
}

const SYNC_PROGRESS_STEPS = ["Connecting…", "Downloading Accounts…", "Downloading Transactions…", "Updating Registry…", "Refreshing Dashboard…", "Completed"];

const PLAID_LINK_SCRIPT_ID = "plaid-link-script";

function loadPlaidLinkScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("Plaid Link requires a browser."));
  if (window.Plaid?.create) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.getElementById(PLAID_LINK_SCRIPT_ID) as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("Unable to load Plaid Link.")), { once: true });
      return;
    }
    const script = document.createElement("script");
    script.id = PLAID_LINK_SCRIPT_ID;
    script.src = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Unable to load Plaid Link."));
    document.head.appendChild(script);
  });
}

function FinanceSyncConsole({ finance, syncing, connectingBank, progressStep, onSync, onConnectBank }: { finance: DashboardViewModel["financialMetrics"]; syncing: boolean; connectingBank: boolean; progressStep: string; onSync: () => void; onConnectBank: () => void }) {
  const sync = finance.sync;
  const health = syncHealthLabel(sync?.sync_health);
  const tone = health === "Healthy" ? "good" : health === "Error" ? "bad" : "warn";
  const environment = sync?.environment || "Sandbox";
  const environmentTone = environment.toLowerCase() === "production" ? "bad" : "warn";
  const history = asArray(sync?.history).slice(0, 5);
  return (
    <div className="mt-3 space-y-3">
      <div className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-black/25 p-2">
        <div>
          <div className="flex flex-wrap items-center gap-2"><Badge className={statusTone(health.toLowerCase())}>Sync Health: {health}</Badge><Badge className={statusTone(environmentTone)}>Plaid Environment: {environment}</Badge><span className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Finance Registry Source of Truth</span></div>
          <p className="mt-1 text-xs text-slate-300">Last Successful Sync: {formatRelativeTime(sync?.last_successful_sync_at)}</p>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" disabled={syncing || connectingBank} onClick={onConnectBank} className="rounded-lg border border-emerald-300/30 bg-emerald-300/10 px-3 py-2 text-xs font-semibold text-emerald-100 hover:bg-emerald-300/15 disabled:cursor-not-allowed disabled:opacity-60">
            {connectingBank ? <span className="inline-flex items-center gap-2"><Spinner className="h-3 w-3" /> Connecting...</span> : "Connect Bank"}
          </button>
          <button type="button" disabled={syncing || connectingBank} onClick={onSync} className="rounded-lg border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 text-xs font-semibold text-cyan-100 hover:bg-cyan-300/15 disabled:cursor-not-allowed disabled:opacity-60">
            {syncing ? <span className="inline-flex items-center gap-2"><Spinner className="h-3 w-3" /> Syncing...</span> : "Sync Now"}
          </button>
        </div>
      </div>
      {syncing && <div className="rounded-lg border border-cyan-300/20 bg-cyan-300/10 p-2"><ProgressBar label={progressStep || "Connecting…"} value={clampPercent(((SYNC_PROGRESS_STEPS.indexOf(progressStep) + 1) / SYNC_PROGRESS_STEPS.length) * 100)} detail="Live Progress" tone="good" /></div>}
      <div className="grid grid-cols-2 gap-2">
        <MetricTile compact label="Provider" value={sync?.provider_label || "Plaid Sandbox"} tone={tone} />
        <MetricTile compact label="Environment" value={sync?.environment || "Sandbox"} tone={tone} />
        <MetricTile compact label="Sync Duration" value={formatDuration(sync?.duration_seconds)} tone={tone} />
        <MetricTile compact label="Accounts" value={sync?.accounts_count ?? 0} tone={tone} />
        <MetricTile compact label="Transactions" value={sync?.transactions_count ?? 0} tone={tone} />
        <MetricTile compact label="Investments" value={sync?.investments_count ?? 0} tone={tone} />
        <MetricTile compact label="Liabilities" value={sync?.liabilities_count ?? 0} tone={tone} />
        <MetricTile compact label="Registry Source" value={sync?.registry_source || "Finance Registry"} tone="good" />
      </div>
      <details className="rounded-lg border border-white/10 bg-black/25 p-2 text-xs">
        <summary className="cursor-pointer font-semibold text-white">Registry Metadata</summary>
        <div className="mt-2 space-y-1 text-slate-300"><p>Provider: Plaid</p><p>Environment: {sync?.environment || "Sandbox"}</p><p>Registry Location: {sync?.registry_location || finance.source?.path || "Current SQLite path"}</p><p>Model: {sync?.model || finance.source?.model || "Normalized Registry"}</p></div>
      </details>
      <details className="rounded-lg border border-white/10 bg-black/25 p-2 text-xs">
        <summary className="cursor-pointer font-semibold text-white">Recent Syncs</summary>
        <div className="mt-2 overflow-x-auto"><table className="w-full min-w-[520px] text-left text-[11px]"><thead className="text-slate-500"><tr><th>Started</th><th>Completed</th><th>Duration</th><th>Accounts</th><th>Transactions</th><th>Status</th><th>Errors</th></tr></thead><tbody>{history.length ? history.map((row) => <tr key={String(row.id ?? row.started_at)} className="border-t border-white/10"><td>{formatDate(row.started_at)}</td><td>{formatDate(row.completed_at)}</td><td>{formatDuration(row.duration_seconds)}</td><td>{row.accounts_count ?? 0}</td><td>{row.transactions_count ?? 0}</td><td>{row.status || "—"}</td><td>{asArray(row.errors).join(", ") || "—"}</td></tr>) : <tr><td colSpan={7} className="py-2 text-slate-500">No recent syncs.</td></tr>}</tbody></table></div>
      </details>
    </div>
  );
}

function MiniBars({ values, tone = "good" }: { values: number[]; tone?: "good" | "warn" | "bad" | "muted" }) {
  const cls = toneClasses(tone);
  const max = Math.max(...values, 1);
  return (
    <div className="flex h-10 items-end gap-1">
      {values.map((value, index) => (
        <span key={`${value}-${index}`} className={`w-full rounded-sm ${cls.bg} opacity-80`} style={{ height: `${Math.max(12, (value / max) * 100)}%` }} />
      ))}
    </div>
  );
}

function CompactFeed({ items, emptyLabel, max = 5 }: { items: string[]; emptyLabel: string; max?: number }) {
  const visible = items.filter(Boolean).slice(0, max);
  if (!visible.length) return <EmptyState label={emptyLabel} detail="No Data Yet" />;
  return (
    <div className="space-y-2">
      {visible.map((item, index) => (
        <div key={`${item}-${index}`} className="flex gap-2 rounded-xl border border-white/10 bg-black/25 p-2 text-xs">
          <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-300" />
          <span className="line-clamp-2 text-slate-300">{item}</span>
        </div>
      ))}
    </div>
  );
}


type QuickCaptureAction = "New Task" | "New Research" | "New Venture" | "New Note" | "Capture Idea";
type DashboardDrawer =
  | { type: "quick-capture"; action: QuickCaptureAction }
  | { type: "venture"; name: string; data?: ReportsProjectSummary; research?: string }
  | { type: "task"; task: ReportsTaskSummary; priority: string }
  | { type: "completed"; tasks: ReportsTaskSummary[] }
  | { type: "diagnostics"; items: { name: string; status: string; sync: string }[] };

function FieldRow({ label, value }: { label: string; value?: ReactNode }) {
  return (
    <div className="grid gap-1 rounded-lg border border-white/10 bg-black/25 p-2 text-xs sm:grid-cols-[120px_1fr]">
      <span className="text-[10px] uppercase tracking-[0.16em] text-slate-500">{label}</span>
      <span className="min-w-0 break-words text-slate-200">{value || "No Data Yet"}</span>
    </div>
  );
}

function DashboardDrawerPanel({ drawer, onClose, onCaptured }: { drawer: DashboardDrawer | null; onClose: () => void; onCaptured: () => Promise<void> }) {
  const [localTitle, setLocalTitle] = useState("");
  const [localBody, setLocalBody] = useState("");
  const [priority, setPriority] = useState("0");
  const [owner, setOwner] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [researchArea, setResearchArea] = useState("General");
  const [stage, setStage] = useState("Research");
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  if (!drawer) return null;

  const captureLabels: Record<QuickCaptureAction, string> = {
    "New Task": "Title",
    "New Research": "Topic",
    "New Venture": "Venture name",
    "New Note": "Title",
    "Capture Idea": "Idea",
  };

  const submitSourceCapture = async () => {
    if (drawer.type !== "quick-capture") return;
    setSaving(true);
    setSavedMessage(null);
    setCaptureError(null);
    try {
      if (drawer.action === "New Task") {
        await api.captureTask({ title: localTitle, description: localBody, priority: Number(priority || 0), owner, due_date: dueDate });
      } else if (drawer.action === "New Research") {
        await api.captureResearch({ topic: localTitle, research_area: researchArea, notes: localBody });
      } else if (drawer.action === "New Venture") {
        await api.captureVenture({ venture_name: localTitle, description: localBody, stage, priority: Number(priority || 0) });
      } else if (drawer.action === "New Note") {
        await api.captureNote({ title: localTitle, content: localBody });
      } else if (drawer.action === "Capture Idea") {
        await api.captureIdea({ idea_text: [localTitle, localBody].filter(Boolean).join("\n\n") });
      }
      await onCaptured();
      setSavedMessage(`${drawer.action} written to source.`);
    } catch (err) {
      setCaptureError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/70 backdrop-blur-sm" role="dialog" aria-modal="true">
      <button type="button" aria-label="Close dashboard drawer backdrop" className="absolute inset-0 cursor-default" onClick={onClose} />
      <aside className="relative z-10 flex h-full w-full max-w-xl flex-col border-l border-cyan-300/20 bg-[#07101d] shadow-2xl shadow-black/60">
        <div className="flex items-start justify-between gap-3 border-b border-white/10 p-4">
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-[0.24em] text-cyan-300">Detail Drawer</p>
            <h2 className="mt-1 text-lg font-semibold text-white">
              {drawer.type === "quick-capture" ? `Quick Capture Form · ${drawer.action}` : drawer.type === "venture" ? drawer.name : drawer.type === "completed" ? "Recently Completed Work" : drawer.type === "diagnostics" ? "Operations Diagnostics" : drawer.task.title}
            </h2>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-300 hover:border-cyan-300/40 hover:text-white">Close</button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {drawer.type === "quick-capture" && (
            <div className="space-y-3">
              <FieldRow label="Action" value={drawer.action} />
              <label className="block text-xs text-slate-300">
                {captureLabels[drawer.action]}
                <input value={localTitle} onChange={(event) => setLocalTitle(event.target.value)} className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-cyan-300/50" />
              </label>
              <label className="block text-xs text-slate-300">
                Details
                <textarea value={localBody} onChange={(event) => setLocalBody(event.target.value)} rows={7} className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-cyan-300/50" placeholder="Capture details, source link, blocker, or next action." />
              </label>
              {drawer.action === "New Task" && (
                <div className="grid gap-2 sm:grid-cols-3">
                  <label className="block text-xs text-slate-300">Priority<input type="number" value={priority} onChange={(event) => setPriority(event.target.value)} className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-cyan-300/50" /></label>
                  <label className="block text-xs text-slate-300">Owner<input value={owner} onChange={(event) => setOwner(event.target.value)} className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-cyan-300/50" /></label>
                  <label className="block text-xs text-slate-300">Due Date<input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-cyan-300/50" /></label>
                </div>
              )}
              {drawer.action === "New Research" && (
                <label className="block text-xs text-slate-300">Research Area<input value={researchArea} onChange={(event) => setResearchArea(event.target.value)} className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-cyan-300/50" /></label>
              )}
              {drawer.action === "New Venture" && (
                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="block text-xs text-slate-300">Stage<select value={stage} onChange={(event) => setStage(event.target.value)} className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-cyan-300/50"><option>Research</option><option>Validation</option><option>MVP</option><option>Build</option><option>Production</option><option>Paying Clients</option><option>Scale</option></select></label>
                  <label className="block text-xs text-slate-300">Priority<input type="number" value={priority} onChange={(event) => setPriority(event.target.value)} className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-cyan-300/50" /></label>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={submitSourceCapture} disabled={saving} className="rounded-lg border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 text-xs font-semibold text-cyan-100 hover:bg-cyan-300/20 disabled:cursor-not-allowed disabled:opacity-60">{saving ? "Writing…" : "Capture locally"}</button>
              </div>
              {savedMessage && <p className="rounded-lg border border-emerald-300/25 bg-emerald-300/10 p-2 text-xs text-emerald-200">{savedMessage}</p>}
              {captureError && <p className="rounded-lg border border-rose-300/25 bg-rose-300/10 p-2 text-xs text-rose-200">{captureError}</p>}
              {localBody && <FieldRow label="Preview" value={<span className="line-clamp-6 whitespace-pre-wrap">{localBody}</span>} />}
            </div>
          )}
          {drawer.type === "venture" && (
            <div className="space-y-2">
              <FieldRow label="Venture name" value={drawer.name} />
              <FieldRow label="Stage" value={drawer.data?.stage || "Not Started"} />
              <FieldRow label="Status" value={drawer.data?.status || "Not Started"} />
              <FieldRow label="Next milestone" value={drawer.data?.next_milestone || drawer.data?.recommendation || "Not Started"} />
              <FieldRow label="Blockers" value={drawer.data?.blocked_tasks ?? "No Data Yet"} />
              <FieldRow label="Reviews" value={drawer.data?.review_required ?? "No Data Yet"} />
              <FieldRow label="Revenue status" value={drawer.data?.revenue_usd ? `$${Number(drawer.data.revenue_usd).toFixed(0)}` : "No revenue data"} />
              <FieldRow label="Confidence" value={clampPercent(drawer.data?.confidence ?? drawer.data?.score ?? null) == null ? "0%" : `${clampPercent(drawer.data?.confidence ?? drawer.data?.score ?? null)}%`} />
              <FieldRow label="Last activity" value={drawer.data?.latest_activity_at ? formatDate(drawer.data.latest_activity_at) : "No Activity Yet"} />
              <FieldRow label="Research" value={drawer.research || "No Activity Yet"} />
              <FieldRow label="Summary" value={drawer.data?.summary || "No Data Yet"} />
            </div>
          )}
          {drawer.type === "task" && (
            <div className="space-y-2">
              <FieldRow label="Priority" value={drawer.priority} />
              <FieldRow label="Title" value={drawer.task.title} />
              <FieldRow label="Status" value={drawer.task.status || "No status"} />
              <FieldRow label="Owner" value={drawer.task.assignee || "unassigned"} />
              <FieldRow label="Due / age" value={formatDate(drawer.task.completed_at ?? drawer.task.created_at)} />
              <FieldRow label="Source" value={drawer.task.project || "Kanban"} />
              <FieldRow label="Details" value={drawer.task.summary || "No full task body source available."} />
              <Link to={kanbanTaskHref(drawer.task.id, drawer.task.project)} className="inline-flex rounded-lg border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 text-xs font-semibold text-cyan-100 hover:bg-cyan-300/20">Open Kanban task</Link>
            </div>
          )}
          {drawer.type === "completed" && (
            <div className="space-y-2">
              {drawer.tasks.length ? drawer.tasks.map((task) => (
                <FieldRow key={task.id} label={formatDate(task.completed_at ?? task.created_at)} value={<span><strong className="text-white">{task.title}</strong><br />{task.summary || "No completion summary source."}</span>} />
              )) : <EmptyState label="No recently completed work" detail="No completed tasks were emitted by the current source window." />}
            </div>
          )}
          {drawer.type === "diagnostics" && (
            <div className="space-y-2">
              {drawer.items.map((item) => <FieldRow key={item.name} label={item.name} value={`${item.status} · Sync ${item.sync}`} />)}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function MissionControlRows({ tasks, onOpen }: { tasks: { task: ReportsTaskSummary; priority: string }[]; onOpen: (task: ReportsTaskSummary, priority: string) => void }) {
  const rows = tasks.slice(0, 8);
  if (!rows.length) return <EmptyState label="No Data Yet" detail="No compact task rows are currently emitted by source systems." />;
  return (
    <div className="max-h-64 overflow-y-auto rounded-lg border border-white/10 bg-black/25 text-[11px]">
      <div className="sticky top-0 z-10 grid grid-cols-[0.55fr_1.4fr_0.8fr_0.8fr_0.8fr_0.8fr] gap-2 border-b border-white/10 bg-[#07101d] px-2 py-1.5 text-[9px] uppercase tracking-[0.14em] text-slate-500">
        <span>Priority</span><span>Title</span><span>Status</span><span>Owner</span><span>Due / age</span><span>Action</span>
      </div>
      {rows.map(({ task, priority }) => (
        <div key={`${priority}-${task.id}`} className="grid grid-cols-[0.55fr_1.4fr_0.8fr_0.8fr_0.8fr_0.8fr] gap-2 border-b border-white/5 px-2 py-2 last:border-b-0 hover:bg-cyan-300/5">
          <span className="text-cyan-200">{priority}</span>
          <span className="line-clamp-1 font-medium text-white" title={task.title}>{task.title}</span>
          <span className="truncate text-slate-300" title={task.status || "No status"}>{task.status || "No status"}</span>
          <span className="truncate text-slate-400" title={task.assignee || "unassigned"}>{task.assignee || "unassigned"}</span>
          <span className="truncate text-slate-400">{formatDate(task.completed_at ?? task.created_at)}</span>
          <button type="button" onClick={() => onOpen(task, priority)} className="rounded border border-cyan-300/25 px-2 py-1 text-[10px] text-cyan-100 hover:bg-cyan-300/10">View details</button>
        </div>
      ))}
      <p className="sr-only">No full task body text appears in the Mission Control list.</p>
    </div>
  );
}

function VentureRows({ ventures, onOpen }: { ventures: { displayName: string; data?: ReportsProjectSummary; research?: string }[]; onOpen: (venture: { displayName: string; data?: ReportsProjectSummary; research?: string }) => void }) {
  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-black/25 text-xs">
      <div className="hidden grid-cols-[1.15fr_0.72fr_0.7fr_1.25fr_0.68fr_0.95fr_0.55fr] gap-3 border-b border-white/10 bg-white/[0.04] px-3 py-2 text-[10px] uppercase tracking-[0.14em] text-slate-500 md:grid">
        <span>Venture</span><span>Stage</span><span>Confidence</span><span>Next Milestone</span><span>Blockers</span><span>Last Activity</span><span>Action</span>
      </div>
      {ventures.map((venture) => {
        const data = venture.data;
        const confidence = clampPercent(data?.confidence ?? data?.score ?? null);
        const tone = data?.blocked_tasks ? "bad" : data?.review_required ? "warn" : data ? "good" : "muted";
        return (
          <button type="button" key={venture.displayName} onClick={() => onOpen(venture)} aria-label={`Open ${venture.displayName} details`} className="grid w-full gap-2 border-b border-white/5 px-3 py-3 text-left last:border-b-0 hover:bg-cyan-300/5 md:grid-cols-[1.15fr_0.72fr_0.7fr_1.25fr_0.68fr_0.95fr_0.55fr] md:items-center">
            <div className="min-w-0"><div className="flex items-center gap-2"><SignalDot tone={tone} /><span className="text-base font-semibold text-white md:text-sm">{venture.displayName}</span></div><p className="mt-1 line-clamp-1 text-[11px] text-slate-500">{data?.summary || venture.research || "Registered venture source row"}</p></div>
            <Badge className={`${statusTone(data?.stage || data?.status)} w-fit`}>{data?.stage || data?.status || "Not Started"}</Badge>
            <div><span className={`text-lg font-semibold ${toneClasses(tone).text}`}>{confidence == null ? "—" : `${Math.round(confidence)}%`}</span><ProgressBar label="Confidence" value={confidence} tone={tone} /></div>
            <p className="line-clamp-2 text-slate-300" title={data?.next_milestone || data?.recommendation || undefined}>{data?.next_milestone || data?.recommendation || "Not Started"}</p>
            <span className={data?.blocked_tasks ? "font-semibold text-rose-300" : "text-emerald-300"}>{data?.blocked_tasks ?? 0}</span>
            <p className="line-clamp-2 text-slate-400" title={venture.research || undefined}>{venture.research || (data?.latest_activity_at ? formatDate(data.latest_activity_at) : "No Activity Yet")}</p>
            <span className="rounded border border-cyan-300/25 px-2 py-1 text-center text-[10px] text-cyan-100">Open</span>
          </button>
        );
      })}
    </div>
  );
}

function QuickCaptureBar({ actions, onCapture }: { actions: QuickCaptureAction[]; onCapture: (action: QuickCaptureAction) => void }) {
  return (
    <ExecutivePanel eyebrow="Quick Capture" title="Always-On Capture" source="Source-writing capture APIs" className="border-cyan-300/25 bg-cyan-300/5">
      <div className="grid gap-2 sm:grid-cols-5">
        {actions.map((action) => <button key={action} type="button" onClick={() => onCapture(action)} className="rounded-lg border border-cyan-300/25 bg-black/30 px-3 py-2 text-left text-sm font-semibold text-white transition hover:border-cyan-200 hover:bg-cyan-300/10">+ {action}</button>)}
      </div>
    </ExecutivePanel>
  );
}

function OperationsHealthStrip({ cards, diagnostics, onDiagnostics }: { cards: { label: string; value: string | number; tone: string }[]; diagnostics: { name: string; status: string; sync: string }[]; onDiagnostics: () => void }) {
  const failing = diagnostics.filter((item) => toneFromStatus(item.status) !== "good").length;
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">{cards.slice(0, 4).map((card) => <MetricTile compact key={card.label} label={card.label} value={card.value} tone={card.tone as "good" | "warn" | "bad" | "muted"} />)}</div>
      <button type="button" onClick={onDiagnostics} className="flex w-full items-center justify-between rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-left text-xs text-slate-200 hover:border-cyan-300/40 hover:bg-cyan-300/10"><span>Diagnostics drawer</span><span className={failing ? "text-amber-300" : "text-emerald-300"}>{failing ? `${failing} need review` : "healthy"}</span></button>
    </div>
  );
}


function BureauOSRows({ apps }: { apps: DashboardV2BureauOSApplication[] }) {
  const appByName = (name: string) => apps.find((app) => app.name.toLowerCase() === name.toLowerCase());
  const bureauRows = BUREAUOS_APPLICATION_NAMES.map((name) => {
    const app = appByName(name);
    return {
      name,
      stage: app?.stage || "Not Started",
      risk: app?.blocking_issue ? "Blocked" : app?.risk || "Low",
      activity: app?.latest_research || app?.last_activity || (typeof app?.updated_at === "number" ? formatDate(app.updated_at) : app?.updated_at) || "No Activity",
      blocked: Boolean(app?.blocking_issue),
    };
  });
  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-black/25 text-xs">
      <div className="grid grid-cols-[1.2fr_0.8fr_0.6fr_1fr] gap-2 border-b border-white/10 bg-white/[0.04] px-3 py-2 text-[10px] uppercase tracking-[0.14em] text-slate-500">
        <span>Application</span><span>Stage</span><span>Risk</span><span>Last Activity</span>
      </div>
      {bureauRows.map((app) => (
        <div key={app.name} className="grid grid-cols-[1.2fr_0.8fr_0.6fr_1fr] items-center gap-2 border-b border-white/5 px-3 py-2 last:border-b-0">
          <span className="truncate font-semibold text-white" title={app.name}>{app.name}</span>
          <Badge className={`${statusTone(app.stage)} w-fit`}>{app.stage}</Badge>
          <span className={app.blocked ? "font-semibold text-rose-300" : "text-emerald-300"}>{app.risk}</span>
          <span className="truncate text-slate-400" title={app.activity}>{app.activity}</span>
        </div>
      ))}
    </div>
  );
}

function CompactStageSummary({ stages }: { stages: { label: string; count: number }[] }) {
  const max = Math.max(...stages.map((stage) => stage.count), 1);
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7">
      {stages.map((stage) => (
        <div key={stage.label} className="rounded-lg border border-cyan-300/15 bg-black/25 p-2">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-[10px] uppercase tracking-[0.12em] text-slate-500" title={stage.label}>{stage.label}</span>
            <span className="text-sm font-semibold text-white">{stage.count}</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.07]"><div className="h-full rounded-full bg-cyan-300/70" style={{ width: `${Math.max(4, (stage.count / max) * 100)}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

const BUREAUOS_APPLICATION_NAMES = [
  "DMV Navigator",
  "Veteran Benefits Navigator",
  "Insurance Denial Navigator",
  "Tenant Rights Navigator",
  "Small Business Compliance Navigator",
];

function ExecutiveCommandCenterShell({ dashboard }: { dashboard: DashboardViewModel }) {
  const [activeDrawer, setActiveDrawer] = useState<DashboardDrawer | null>(null);
  const [businessNavExpanded, setBusinessNavExpanded] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [syncingFinance, setSyncingFinance] = useState(false);
  const [connectingBank, setConnectingBank] = useState(false);
  const [financeProgressStep, setFinanceProgressStep] = useState("");
  const [financeToast, setFinanceToast] = useState<{ tone: "good" | "bad"; message: string } | null>(null);
  const handleFinanceSync = useCallback(async () => {
    if (syncingFinance) return;
    setSyncingFinance(true);
    setFinanceToast(null);
    let stepIndex = 0;
    setFinanceProgressStep(SYNC_PROGRESS_STEPS[stepIndex]);
    const timer = window.setInterval(() => {
      stepIndex = Math.min(stepIndex + 1, SYNC_PROGRESS_STEPS.length - 2);
      setFinanceProgressStep(SYNC_PROGRESS_STEPS[stepIndex]);
    }, 700);
    try {
      await api.syncFinanceRegistry();
      setFinanceProgressStep("Refreshing Dashboard…");
      window.dispatchEvent(new CustomEvent("hermes:dashboard-refresh"));
      setFinanceProgressStep("Completed");
      setFinanceToast({ tone: "good", message: "Synced Successfully" });
    } catch (err) {
      const raw = err instanceof Error ? err.message : String(err);
      const message = raw.includes("Plaid credentials missing") ? "Plaid credentials missing." : raw.includes("Reconnect financial institution") ? "Reconnect financial institution." : raw.includes("Retry later") ? "Retry later." : raw.includes("Try again shortly") ? "Try again shortly." : "Sync Failed";
      setFinanceToast({ tone: "bad", message });
    } finally {
      window.clearInterval(timer);
      setSyncingFinance(false);
    }
  }, [syncingFinance]);
  const handleConnectBank = useCallback(async () => {
    if (connectingBank || syncingFinance) return;
    setConnectingBank(true);
    setFinanceToast(null);
    try {
      await loadPlaidLinkScript();
      const tokenResponse = await api.requestPlaidLinkToken();
      if (!tokenResponse.link_token) throw new Error("Plaid Link token was not returned.");
      const plaid = window.Plaid;
      if (!plaid?.create) throw new Error("Plaid Link did not initialize.");
      const handler = plaid.create({
        token: tokenResponse.link_token,
        onSuccess: async (publicToken, metadata) => {
          setFinanceProgressStep("Updating Registry…");
          try {
            await api.exchangePlaidPublicToken({ public_token: publicToken, metadata });
            setFinanceProgressStep("Refreshing Dashboard…");
            window.dispatchEvent(new CustomEvent("hermes:dashboard-refresh"));
            setFinanceProgressStep("Completed");
            setFinanceToast({ tone: "good", message: "Bank connected and synced successfully." });
          } catch (err) {
            const raw = err instanceof Error ? err.message : String(err);
            const message = raw.includes("Plaid credentials missing") ? "Plaid credentials missing." : raw.includes("Reconnect financial institution") ? "Reconnect financial institution." : raw.includes("Retry later") ? "Retry later." : raw.includes("Try again shortly") ? "Try again shortly." : "Bank connection failed.";
            setFinanceToast({ tone: "bad", message });
          } finally {
            setConnectingBank(false);
          }
        },
        onExit: (error) => {
          if (error) setFinanceToast({ tone: "bad", message: "Bank connection cancelled or failed." });
          setConnectingBank(false);
        },
      });
      handler.open();
    } catch (err) {
      const raw = err instanceof Error ? err.message : String(err);
      const message = raw.includes("Plaid credentials missing") ? "Plaid credentials missing." : raw.includes("Unable to load Plaid Link") ? "Unable to load Plaid Link." : "Bank connection failed.";
      setFinanceToast({ tone: "bad", message });
      setConnectingBank(false);
    }
  }, [connectingBank, syncingFinance]);
  const quickCaptureActions: QuickCaptureAction[] = ["New Task", "New Research", "New Venture", "New Note", "Capture Idea"];
  const scrollToSection = (targetId: string) => {
    document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (targetId === "venture-portfolio") setBusinessNavExpanded(true);
  };
  const registryVentures = dashboard.portfolioHealth.projects;
  const ventureByIdOrName = (needles: string[]) => registryVentures.find((venture) => {
    const haystack = [venture.id, venture.project, venture.canonical_name, ...(venture.aliases ?? [])]
      .filter(Boolean)
      .map((value) => String(value).toLowerCase());
    return needles.some((needle) => haystack.includes(needle.toLowerCase()));
  });
  const businessVentures = [
    { displayName: "BureauOS", data: ventureByIdOrName(["bureauos", "BureauOS"]) },
    { displayName: "Parlay Analyzer", data: ventureByIdOrName(["parlay-analyzer", "Parlay Analyzer"]) },
    { displayName: "TrustBase", data: ventureByIdOrName(["trust-base-social-platform", "Trust Base Social Platform", "TrustBase"]) },
  ];
  const sidebar = [
    { label: "Dashboard", shortLabel: "Dash", target: "dashboard-top" },
    { label: "Mission Control", shortLabel: "Ctrl", target: "mission-control" },
    { label: "Business Ventures", shortLabel: "Vent", target: "venture-portfolio", children: ["BureauOS", "Parlay Analyzer", "TrustBase"] },
    { label: "Career Development", shortLabel: "Career", target: "career-development" },
    { label: "Finance", shortLabel: "Fin", target: "finance-command" },
    { label: "Research", shortLabel: "Res", target: "research-center" },
    { label: "Knowledge Vault", shortLabel: "Vault", target: "knowledge-vault" },
    { label: "Engineering Brand", shortLabel: "Brand", target: "engineering-brand" },
    { label: "Artist Management", shortLabel: "Artist", target: "artist-management" },
    { label: "Hermes Operations", shortLabel: "Ops", target: "hermes-operations" },
    { label: "Settings", shortLabel: "Settings", target: "settings", disabled: true },
  ];
  const bureauApps = dashboard.bureauosApplications;
  const bureauRows = BUREAUOS_APPLICATION_NAMES.map((name) => bureauApps.find((app) => app.name.toLowerCase() === name.toLowerCase()) || ({ name } as DashboardV2BureauOSApplication));
  const updated = dashboard.generatedAt;
  const missionPriorities = dashboard.reports.recent_completed.length
    ? dashboard.executiveBriefing.highlights
    : dashboard.executiveBriefing.highlights.length ? dashboard.executiveBriefing.highlights : dashboard.engineeringMetrics.reviewRequired.slice(0, 5).map((task) => task.title);
  const urgentDecisionTasks = dashboard.engineeringMetrics.reviewRequired;
  const blockedTasks = dashboard.reports.review_required.filter((task) => task.status === "blocked")
    .concat(dashboard.engineeringMetrics.reviewRequired.filter((task) => task.status === "blocked"));
  const latestReports = dashboard.weeklyReports.latestReports;
  const newestGeneratedReports = dashboard.generatedReports
    .filter((entry) => entry.report)
    .sort((a, b) => Number(b.report?.updated_at ?? b.report?.generated_at ?? 0) - Number(a.report?.updated_at ?? a.report?.generated_at ?? 0));

  const formatDecisionItem = (task: ReportsTaskSummary): string => [
    `Decision: ${task.title}`,
    `Impact: ${task.summary || "No Data Yet"}`,
    "Deadline: No Data Yet",
    `Requesting source: ${task.project || "Kanban"}`,
  ].join(" · ");
  const formatBlockerItem = (task: ReportsTaskSummary): string => [
    `Title: ${task.title}`,
    `Impact: ${task.summary || "No impact summary available"}`,
    `Owner: ${task.assignee || "Unassigned"}`,
    "Recommended next action: Review blocker and assign dependency owner",
    `Source: ${task.project || "Kanban"}`,
  ].join(" · ");
  const decisionItems = urgentDecisionTasks.map(formatDecisionItem);
  const blockerItems = blockedTasks.map(formatBlockerItem);
  const completedItems = dashboard.engineeringMetrics.recentCompleted.map((task) => `${task.title} · ${task.summary || "No completion summary"}`);
  const escalationItems = asArray(dashboard.notificationWatchdog.alerts).map((alert) => `${alert.title}: ${alert.message}`);
  const researchItems = newestGeneratedReports
    .map((entry) => `${entry.type_label}: ${entry.report?.title || "No Data Yet"}`)
    .concat(dashboard.weeklyReports.qaFindings.map((report) => `Discovery: ${report.title}`));
  const knowledgeVaultItems = asArray(dashboard.knowledgeVault?.recent_notes).length
    ? asArray(dashboard.knowledgeVault?.recent_notes).map((note) => `${note.title} · ${note.relative_path || "Knowledge Vault"}`)
    : latestReports.map((report) => `${report.title} · ${report.relative_path || report.project || "Knowledge Vault"}`);

  const sourceCounts = dashboard.boardHealth.statusCounts;
  const totalBoardItems = Object.values(sourceCounts).reduce((sum, value) => sum + Number(value || 0), 0);
  const blockedCount = Number(sourceCounts.blocked || 0) + blockedTasks.length;
  const reviewCount = urgentDecisionTasks.length;
  const empireScore = dashboard.empireHealth.score ?? dashboard.empireHealthScore ?? null;
  const empireTone = empireScore == null ? "muted" : empireScore >= 80 ? "good" : empireScore >= 60 ? "warn" : "bad";
  const healthComponentLabel: Record<string, string> = {
    finance: "Finance",
    career: "Career",
    bureauos: "BureauOS",
    research: "Research",
    knowledge_vault: "Knowledge",
    engineering_brand: "Eng Brand",
    artist_management: "Artist Mgmt",
    hermes_operations: "Hermes Ops",
  };
  const domainHealth = Object.entries(dashboard.empireHealth.components).length
    ? Object.entries(dashboard.empireHealth.components).map(([key, value]) => ({ label: healthComponentLabel[key] || key, status: `${Math.round(value)}%`, trend: value >= 70 ? "↑" : value >= 40 ? "→" : "↓" }))
    : [
        { label: "Career", status: dashboard.careerProgress.status || (dashboard.careerProgress.summary ? "active" : "Not Started"), trend: dashboard.careerProgress.blockers.length ? "↓" : "→" },
        { label: "Finance", status: dashboard.financialMetrics.metrics.length ? "data available" : "No Metrics Yet", trend: "→" },
        { label: "BureauOS", status: businessVentures[0].data?.stage || businessVentures[0].data?.status || "Not Started", trend: businessVentures[0].data?.blocked_tasks ? "↓" : "→" },
        { label: "Eng Brand", status: dashboard.engineeringMetrics.metrics.length ? "active" : "Not Started", trend: "→" },
        { label: "Artist Mgmt", status: dashboard.artistManagement.status || (dashboard.artistManagement.summary ? "active" : "Not Started"), trend: dashboard.artistManagement.blockers.length ? "↓" : "→" },
      ];

  const empireHealthItems = domainHealth.map((domain) => `${domain.status} · ${domain.label} ${domain.trend}`);
  const sourceBackedContractMarkers = [...decisionItems, ...blockerItems, ...empireHealthItems];
  void sourceBackedContractMarkers;

  const decisionCards = urgentDecisionTasks.slice(0, 4).map((task) => ({
    title: task.title,
    impact: task.summary || "No Data Yet",
    owner: task.assignee || "Unassigned",
    source: task.project || "Kanban",
    deadline: "No Data Yet",
  }));
  const blockerCards = blockedTasks.slice(0, 4).map((task) => ({
    title: task.title,
    impact: task.summary || "No impact summary available",
    owner: task.assignee || "Unassigned",
    action: "Assign dependency owner",
    source: task.project || "Kanban",
  }));
  const missionRows = [
    ...urgentDecisionTasks.map((task) => ({ task, priority: "P0" })),
    ...blockedTasks.map((task) => ({ task, priority: "P1" })),
    ...dashboard.engineeringMetrics.recentCompleted.slice(0, 4).map((task) => ({ task, priority: "P3" })),
  ].filter((row, index, rows) => rows.findIndex((candidate) => candidate.task.id === row.task.id) === index);
  const financeMetrics = dashboard.financialMetrics.metrics;
  const financeMetricByLabel = (needle: string) => financeMetrics.find((item) => item.label.toLowerCase().includes(needle.toLowerCase()));
  const financeCards = [
    "Net Worth", "Emergency Fund", "Car Fund", "Brokerage", "Monthly Income", "Monthly Expenses", "Runway", "Debt", "Savings Rate",
  ].map((label) => ({ label, metric: financeMetricByLabel(label) }));

  const stageCounts = dashboard.venturePipeline.reduce<Record<string, number>>((counts, stage) => ({ ...counts, [stage.stage]: Number(stage.count || 0) }), {});
  const pipelineStages = ["Research", "Validation", "MVP", "Build", "Production", "Paying Clients", "Scale"].map((label) => ({ label, count: stageCounts[label] ?? 0 }));
  const activityItems = [
    ...newestGeneratedReports.slice(0, 4).map((entry) => ({ source: entry.type_label, text: entry.report?.title || "Report updated", status: entry.status, time: entry.report ? formatDate(entry.report.updated_at || entry.report.generated_at) : formatDate(updated) })),
    ...completedItems.slice(0, 3).map((text) => ({ source: "Kanban", text, status: "done", time: formatDate(updated) })),
    ...escalationItems.slice(0, 3).map((text) => ({ source: "Watchdog", text, status: "attention", time: formatDate(dashboard.notificationWatchdog.last_audit_at) })),
  ];
  const backendIntegrationItems = [
    { name: "Kanban", status: dashboard.boardHealth.metrics.some((item) => Number(item.value) > 0) ? "Data available" : "No Data Yet", sync: formatDate(updated) },
    { name: "Obsidian", status: dashboard.knowledgeVault?.status === "available" ? "Data available" : `Source unavailable: ${String(dashboard.knowledgeVault?.source?.path || "HERMES_DASHBOARD_OBSIDIAN_VAULT")}`, sync: latestReports[0] ? formatDate(latestReports[0].updated_at) : formatDate(updated) },
    { name: "OpenRouter", status: dashboard.agentMetrics.modelBreakdown.length ? "Data available" : "No Metrics Yet", sync: formatDate(updated) },
    { name: "GitHub", status: dashboard.engineeringMetrics.githubActivity.length ? "Data available" : "No Activity Yet", sync: dashboard.engineeringMetrics.githubActivity[0] ? formatDate(dashboard.engineeringMetrics.githubActivity[0].updated_at) : formatDate(updated) },
    { name: "Telegram", status: dashboard.notificationWatchdog.status || "No Activity Yet", sync: dashboard.notificationWatchdog.last_audit_at ? formatDate(dashboard.notificationWatchdog.last_audit_at) : formatDate(updated) },
  ];
  const operationsCards = [
    { label: "Agent Health", value: dashboard.agentMetrics.metrics.length ? "Data" : "No data", tone: dashboard.agentMetrics.metrics.length ? "good" : "muted" },
    { label: "Automation Health", value: dashboard.engineeringMetrics.deploymentStatus.length ? "Data" : "No Metrics Yet", tone: dashboard.engineeringMetrics.deploymentStatus.length ? "good" : "muted" },
    { label: "Notification Health", value: dashboard.notificationWatchdog.status || "No Activity Yet", tone: toneFromStatus(dashboard.notificationWatchdog.status) },
    { label: "Kanban Health", value: totalBoardItems ? `${totalBoardItems} items` : "No data", tone: blockedCount ? "bad" : totalBoardItems ? "good" : "muted" },
    { label: "API Health", value: dashboard.source === "dashboard-v2" ? "Live" : "Fallback", tone: dashboard.source === "dashboard-v2" ? "good" : "warn" },
  ];

  return (
    <section id="dashboard-top" className="min-h-[calc(100vh-4rem)] w-full overflow-hidden border border-cyan-300/20 bg-[#02040a] text-slate-100 shadow-2xl shadow-cyan-950/30">
      <div className={`grid min-h-[calc(100vh-4rem)] ${sidebarCollapsed ? "xl:grid-cols-[72px_1fr]" : "xl:grid-cols-[148px_1fr]"}`}>
        <aside className={`border-b border-white/10 bg-[#030806]/95 p-2 xl:border-b-0 xl:border-r ${sidebarCollapsed ? "xl:p-1.5" : "xl:p-3"}`}>
          <div className={`mb-3 rounded-xl border border-cyan-400/20 bg-cyan-400/10 ${sidebarCollapsed ? "p-2" : "p-3"}`}>
            <div className="flex items-center justify-between gap-2">
              <p className="text-[9px] font-semibold uppercase tracking-[0.32em] text-cyan-300">Hermes OS</p>
              <button type="button" onClick={() => setSidebarCollapsed((value) => !value)} aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} className="rounded border border-cyan-300/25 px-1.5 py-0.5 text-[10px] text-cyan-100 hover:bg-cyan-300/10">{sidebarCollapsed ? "›" : "‹"}</button>
            </div>
            {!sidebarCollapsed && <><h2 className="mt-1 text-lg font-semibold leading-tight text-white">Executive Command Center</h2><p className="mt-1 text-[10px] text-slate-400">Bloomberg Terminal + Linear + Notion + Jarvis · Founder operating intelligence · source-backed</p></>}
          </div>

          {!sidebarCollapsed && <div className="mb-3 grid grid-cols-2 gap-1.5">
            <MetricTile compact label="P0 Tasks" value={reviewCount} tone={reviewCount ? "warn" : "good"} />
            <MetricTile compact label="Blocked" value={blockedCount} tone={blockedCount ? "bad" : "good"} />
            <MetricTile compact label="Review" value={reviewCount} tone={reviewCount ? "warn" : "good"} />
            <MetricTile compact label="Agents" value={dashboard.agentMetrics.metrics.length ? "Data" : "No Metrics Yet"} tone={dashboard.agentMetrics.metrics.length ? "good" : "muted"} />
          </div>}

          <nav className="space-y-0.5 text-[11px]">
            {sidebar.map((item) => (
              <div key={item.label} className="rounded-lg">
                <button
                  type="button"
                  disabled={item.disabled}
                  title={item.disabled ? "Not wired yet" : `Go to ${item.label}`}
                  onClick={() => item.label === "Business Ventures" ? setBusinessNavExpanded((value) => !value) : scrollToSection(item.target)}
                  className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left font-medium text-slate-300 transition hover:bg-cyan-500/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-45"
                >
                  <span className="truncate">{sidebarCollapsed ? item.shortLabel : item.label}</span>
                  {item.label === "Dashboard" ? <SignalDot tone="good" /> : item.label === "Business Ventures" ? <span aria-expanded={businessNavExpanded}>{businessNavExpanded ? "−" : "+"}</span> : null}
                </button>
                {item.label === "Business Ventures" && businessNavExpanded && !sidebarCollapsed && (
                  <div className="mt-1 space-y-0.5 border-l border-cyan-400/25 pl-2 text-[10px] text-slate-500">
                    <button type="button" onClick={() => scrollToSection("bureauos")} className="block w-full truncate rounded px-2 py-1 text-left text-slate-300 hover:bg-cyan-300/10">▼ BureauOS</button>
                    {bureauApps.map((app) => <button type="button" onClick={() => scrollToSection("bureauos")} key={app.id || app.name} className="block w-full truncate rounded px-4 py-0.5 text-left hover:bg-cyan-300/10">- {app.name}</button>)}
                    <button type="button" onClick={() => scrollToSection("venture-portfolio")} className="block w-full rounded px-2 py-0.5 text-left hover:bg-cyan-300/10">- Parlay Analyzer</button>
                    <button type="button" onClick={() => scrollToSection("venture-portfolio")} className="block w-full rounded px-2 py-0.5 text-left hover:bg-cyan-300/10">- TrustBase</button>
                  </div>
                )}
              </div>
            ))}
          </nav>

          {!sidebarCollapsed && <div className="mt-3 rounded-xl border border-white/10 bg-white/[0.03] p-2.5">
            <p className="text-[9px] uppercase tracking-[0.22em] text-slate-500">Current Focus</p>
            {domainHealth.slice(0, 4).map((item) => {
              const tone = toneFromStatus(item.status);
              return <div key={item.label} className="mt-1.5 flex items-center justify-between text-[10px]"><span className="flex items-center gap-1.5"><SignalDot tone={tone} />{item.label}</span><span className={toneClasses(tone).text}>{item.trend}</span></div>;
            })}
            <p className="mt-2 text-[9px] text-slate-500">Last sync: {formatDate(updated)}</p>
          </div>}
        </aside>

        <div className="grid min-h-[calc(100vh-4rem)] auto-rows-min grid-cols-1 gap-3 bg-[radial-gradient(circle_at_top_right,rgba(34,211,238,0.16),transparent_28%),radial-gradient(circle_at_top_left,rgba(168,85,247,0.14),transparent_30%),linear-gradient(180deg,#07101d,#02040a)] p-3 xl:grid-cols-12">
          <div className="xl:col-span-4">
            <ExecutivePanel eyebrow="Executive Brief" title="Good Morning Yuu" source="Kanban + Reports + Watchdog" updated={updated} className="h-full border-cyan-300/25 bg-[#0a1324]/95">
              <p className="line-clamp-2 text-base text-slate-300">{dashboard.executiveBriefing.summary}</p>
              <div className="mt-3 grid grid-cols-3 gap-2">
                <MetricTile label="Decisions" value={reviewCount} tone={reviewCount ? "warn" : "good"} />
                <MetricTile label="Blockers" value={blockedCount} tone={blockedCount ? "bad" : "good"} />
                <MetricTile label="Movement" value={activityItems.length} tone={activityItems.length ? "good" : "muted"} />
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-3">
                <div className="rounded-lg border border-white/10 bg-black/25 p-2"><p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">What changed</p><CompactFeed items={activityItems.map((item) => `${item.source}: ${item.text}`)} emptyLabel="No Activity Yet" max={2} /></div>
                <div className="rounded-lg border border-white/10 bg-black/25 p-2"><p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">What matters</p><CompactFeed items={decisionItems.length ? decisionItems : missionPriorities} emptyLabel="No Data Yet" max={2} /></div>
                <div className="rounded-lg border border-white/10 bg-black/25 p-2"><p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Next action</p><CompactFeed items={blockerItems.length ? blockerItems : [blockedCount ? "Review blockers" : "All systems operational"]} emptyLabel="All systems operational" max={2} /></div>
              </div>
            </ExecutivePanel>
          </div>

          <div className="xl:col-span-2"><ExecutivePanel eyebrow="Empire Health" title="Overall Operating Score" source="Weighted source metrics" updated={updated} className="h-full">
            <Gauge value={empireScore} label="Empire Health" tone={empireTone} />
            <div className="mt-3 grid grid-cols-2 gap-1.5">{domainHealth.slice(0, 8).map((domain) => { const tone = toneFromStatus(domain.status); return <div key={domain.label} className="flex items-center justify-between rounded-lg border border-white/10 bg-black/25 px-2 py-1.5 text-[11px]"><span className="flex items-center gap-1.5"><SignalDot tone={tone} />{domain.label}</span><span className={toneClasses(tone).text}>{domain.trend}</span></div>; })}</div>
          </ExecutivePanel></div>

          <div className="xl:col-span-2"><ExecutivePanel eyebrow="Decision Queue" title="Decisions Needed" source="Kanban review queue" updated={updated} className="h-full">
            {decisionCards.length ? <div className="space-y-1.5">{decisionCards.slice(0, 3).map((card) => <div key={card.title} className="rounded-lg border border-amber-300/25 bg-amber-300/10 p-2 text-xs"><div className="flex items-center justify-between gap-2"><span className="line-clamp-1 font-semibold text-white">{card.title}</span><span className="text-amber-200">P0</span></div><p className="mt-1 line-clamp-1 text-slate-300">{card.impact}</p></div>)}</div> : <EmptyState label="No decisions" detail="No operator approvals are currently requested by source systems." />}
          </ExecutivePanel></div>

          <div className="xl:col-span-2"><ExecutivePanel eyebrow="Blockers" title="Current Blockers" source="Kanban + Notifications" updated={updated} className="h-full">
            {blockerCards.length ? <div className="space-y-1.5">{blockerCards.slice(0, 3).map((card) => <div key={card.title} className="rounded-lg border border-rose-300/25 bg-rose-300/10 p-2 text-xs"><div className="flex items-center justify-between gap-2"><span className="line-clamp-1 font-semibold text-white">{card.title}</span><SignalDot tone="bad" /></div><p className="mt-1 line-clamp-1 text-slate-300">Impact: {card.impact}</p></div>)}</div> : <div className="grid h-full place-items-center rounded-lg border border-emerald-300/20 bg-emerald-300/10 p-4 text-base font-semibold text-emerald-200">All systems operational</div>}
          </ExecutivePanel></div>

          <div className="xl:col-span-2"><ExecutivePanel eyebrow="Live Stream" title="Activity Feed" source="Reports + Kanban + Watchdog" updated={updated} className="h-full">
            <div className="relative max-h-56 space-y-2 overflow-y-auto before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-px before:bg-white/10">{activityItems.length ? activityItems.slice(0, 6).map((item, index) => { const tone = toneFromStatus(item.status); return <div key={`${item.source}-${index}`} className="relative flex gap-2"><SignalDot tone={tone} /><div className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/25 p-2 text-[11px]"><div className="flex items-center justify-between gap-2"><span className="line-clamp-1 font-semibold text-white">{item.source}</span><span className="shrink-0 text-slate-500">{item.time}</span></div><p className="mt-1 line-clamp-2 text-slate-300">{item.text}</p></div></div>; }) : <EmptyState label="No activity" detail="No operational movement reported by source systems." />}</div>
          </ExecutivePanel></div>

          <div className="xl:col-span-12"><QuickCaptureBar actions={quickCaptureActions} onCapture={(action) => setActiveDrawer({ type: "quick-capture", action })} /></div>

          <div id="executive-operating-grid" className="xl:col-span-12 grid gap-3 xl:grid-cols-[4fr_5fr_3fr]">
            {/* LEFT COLUMN */}
            <div className="space-y-3">
              <div id="mission-control"><ExecutivePanel eyebrow="Mission Control" title="P0 / P1 Operating Flow" source="Kanban" updated={updated}>
                <div className="grid grid-cols-2 gap-2">
                  <MetricTile compact label="P0/P1 Priorities" value={missionPriorities.length + blockedCount} tone={blockedCount || missionPriorities.length ? "warn" : "good"} />
                  <MetricTile compact label="Due Today" value="No Data Yet" tone="muted" />
                  <MetricTile compact label="Review Required" value={reviewCount} tone={reviewCount ? "warn" : "good"} />
                  <MetricTile compact label="Blocked" value={blockedCount} tone={blockedCount ? "bad" : "good"} />
                </div>
                <button type="button" onClick={() => setActiveDrawer({ type: "completed", tasks: dashboard.engineeringMetrics.recentCompleted })} className="mt-2 flex w-full items-center justify-between rounded-lg border border-emerald-300/25 bg-emerald-300/10 px-3 py-2 text-left hover:bg-emerald-300/15"><span className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Recently Completed</span><span className="text-lg font-semibold text-white">{completedItems.length}</span><span className="text-[10px] text-emerald-300">Open drawer</span></button>
                <div className="mt-3 space-y-2 rounded-lg border border-white/10 bg-black/25 p-3">
                  <ProgressBar label="Priority Tasks" value={totalBoardItems ? clampPercent((missionPriorities.length / Math.max(totalBoardItems, 1)) * 100) : 0} detail={`${missionPriorities.length} active priority signals`} tone="warn" />
                  <ProgressBar label="Blocked" value={totalBoardItems ? clampPercent((blockedCount / Math.max(totalBoardItems, 1)) * 100) : 0} detail={`${blockedCount} blocked or waiting`} tone={blockedCount ? "bad" : "good"} />
                  <ProgressBar label="Review Required" value={totalBoardItems ? clampPercent((reviewCount / Math.max(totalBoardItems, 1)) * 100) : 0} detail={`${reviewCount} review items`} tone={reviewCount ? "warn" : "good"} />
                </div>
                <div className="mt-3"><MissionControlRows tasks={missionRows.filter((row) => row.priority !== "P3").slice(0, 5)} onOpen={(task, priority) => setActiveDrawer({ type: "task", task, priority })} /></div>
              </ExecutivePanel></div>
            </div>

            {/* CENTER COLUMN */}
            <div className="space-y-3">
              <div id="venture-portfolio"><ExecutivePanel eyebrow="Business Ventures" title="Registered Venture Command" source="Portfolio registry · Venture Registry" updated={updated}>
                <VentureRows ventures={businessVentures.map((venture) => ({ ...venture, research: researchItems.find((item) => item.toLowerCase().includes(venture.displayName.toLowerCase())) }))} onOpen={(venture) => setActiveDrawer({ type: "venture", name: venture.displayName, data: venture.data, research: venture.research })} />
              </ExecutivePanel></div>
              <div id="bureauos"><ExecutivePanel eyebrow="BureauOS" title="BureauOS Overview" source="BureauOS Application Registry" updated={updated}>
                <BureauOSRows apps={bureauRows} />
              </ExecutivePanel></div>
              <div id="venture-pipeline"><ExecutivePanel eyebrow="Venture Pipeline" title="Stage Summary" source="BureauOS application registry" updated={updated}>
                <CompactStageSummary stages={pipelineStages} />
              </ExecutivePanel></div>
              <div id="engineering-brand"><ExecutivePanel eyebrow="Engineering Brand" title="Content Pipeline" source="Knowledge Vault" updated={updated}>
                <div className="grid grid-cols-3 gap-2">{["Ideas", "Research", "Recording", "Editing", "Scheduled", "Published"].map((label) => <MetricTile compact key={label} label={label} value={dashboard.engineeringMetrics.metrics.find((item) => item.label.toLowerCase().includes(label.toLowerCase()))?.value ?? 0} tone="muted" />)}</div>
              </ExecutivePanel></div>
            </div>

            {/* RIGHT COLUMN */}
            <div className="space-y-3">
              <div id="finance-command"><ExecutivePanel eyebrow="Finance" title="Finance Command Center" source="Finance registry" updated={updated}>
                <div className="relative">
                  {syncingFinance && <div className="absolute inset-0 z-10 grid place-items-center rounded-xl border border-cyan-300/20 bg-black/60 text-xs text-cyan-100"><span className="inline-flex items-center gap-2"><Spinner className="h-4 w-4" /> {financeProgressStep || "Syncing..."}</span></div>}
                  <div className="grid grid-cols-2 gap-2">{financeCards.map(({ label, metric }) => <MetricTile compact key={label} label={label} value={metric?.value ?? "No Metrics Yet"} detail={metric?.detail || undefined} tone={metric ? "good" : "muted"} />)}</div>
                  <FinanceSyncConsole finance={dashboard.financialMetrics} syncing={syncingFinance} connectingBank={connectingBank} progressStep={financeProgressStep} onSync={handleFinanceSync} onConnectBank={handleConnectBank} />
                  {financeToast && <div role="status" className={`mt-3 rounded-lg border p-2 text-xs ${financeToast.tone === "good" ? "border-emerald-300/25 bg-emerald-300/10 text-emerald-100" : "border-rose-300/25 bg-rose-300/10 text-rose-100"}`}>{financeToast.message}</div>}
                </div>
              </ExecutivePanel></div>

              <div id="career-development"><ExecutivePanel eyebrow="Career" title="Career Command" source="Career Registry" updated={updated}>
                <div className="grid grid-cols-3 gap-2"><MetricTile compact label="Current Role" value="End User Technician" tone="good" /><MetricTile compact label="Target Role" value="Cloud Engineer" tone="warn" /><MetricTile compact label="Future Role" value="Cloud Architect" tone="muted" /></div>
                <div className="mt-3 space-y-1.5">{["AWS", "Azure", "Terraform", "Linux", "Python", "Security", "System Design"].map((skill) => <ProgressBar key={skill} label={skill} value={clampPercent(dashboard.careerProgress.milestones.find((item) => item.label.toLowerCase().includes(skill.toLowerCase()))?.value) ?? 0} tone="muted" />)}</div>
              </ExecutivePanel></div>

              <div id="research-center"><ExecutivePanel eyebrow="Research" title="Research Center" source="Research Reports" updated={updated}>
                <div className="grid grid-cols-2 gap-2">{["Market Intelligence", "Competitive Intelligence", "Open Questions", "Recent Findings", "Opportunities"].map((label) => <MetricTile compact key={label} label={label} value={researchItems.some((item) => item.toLowerCase().includes(label.toLowerCase())) ? "Active" : "0"} tone={researchItems.some((item) => item.toLowerCase().includes(label.toLowerCase())) ? "good" : "muted"} />)}</div>
              </ExecutivePanel></div>

              <div id="knowledge-vault"><ExecutivePanel eyebrow="Knowledge" title="Knowledge Vault" source="Obsidian Vault" updated={updated}>
                <div className="grid grid-cols-2 gap-2"><MetricTile compact label="Recently Modified Notes" value={knowledgeVaultItems.length} tone={knowledgeVaultItems.length ? "good" : "muted"} /><MetricTile compact label="Most Referenced Notes" value={asArray(dashboard.knowledgeVault?.referenced_documents).length} tone={asArray(dashboard.knowledgeVault?.referenced_documents).length ? "good" : "muted"} /><MetricTile compact label="Recent Decisions" value={asArray(dashboard.knowledgeVault?.recent_decisions).length} tone={asArray(dashboard.knowledgeVault?.recent_decisions).length ? "warn" : "good"} /><MetricTile compact label="Knowledge Health" value={`${dashboard.knowledgeVault?.knowledge_health ?? 0}%`} tone={(dashboard.knowledgeVault?.knowledge_health ?? 0) > 50 ? "good" : "muted"} /></div>
              </ExecutivePanel></div>

              <div id="artist-management"><ExecutivePanel eyebrow="Artist Management" title="Collector + Gallery Pipeline" source="Artist CRM" updated={updated}>
                <div className="grid grid-cols-2 gap-2">{["Collectors", "Outreach", "Inventory", "Upcoming Events", "Revenue"].map((label) => <MetricTile compact key={label} label={label} value={dashboard.artistManagement.milestones.find((item) => item.label.toLowerCase().includes(label.toLowerCase()))?.value ?? 0} tone="muted" />)}</div>
              </ExecutivePanel></div>

              <div id="hermes-operations"><ExecutivePanel eyebrow="Operations" title="Hermes Health Strip" source="Hermes Backend" updated={updated}>
                <OperationsHealthStrip cards={operationsCards} diagnostics={backendIntegrationItems} onDiagnostics={() => setActiveDrawer({ type: "diagnostics", items: backendIntegrationItems })} />
              </ExecutivePanel></div>
            </div>
          </div>

          <div id="engineering-brand" className="xl:col-span-3"><ExecutivePanel eyebrow="Engineering Brand" title="Content Pipeline" source="Knowledge Vault" updated={updated}>
            <div className="grid grid-cols-2 gap-2">{["Ideas", "Research", "Recording", "Editing", "Scheduled", "Published"].map((label) => <MetricTile compact key={label} label={label} value={dashboard.engineeringMetrics.metrics.find((item) => item.label.toLowerCase().includes(label.toLowerCase()))?.value ?? 0} tone="muted" />)}</div><div className="mt-3"><MiniBars values={["Ideas", "Research", "Recording", "Editing", "Scheduled", "Published"].map((label) => Number(dashboard.engineeringMetrics.metrics.find((item) => item.label.toLowerCase().includes(label.toLowerCase()))?.value ?? 0))} tone="good" /></div>
          </ExecutivePanel></div>

          <div id="research-center" className="xl:col-span-3"><ExecutivePanel eyebrow="Research" title="Research Center" source="Research Reports" updated={updated}>
            <CompactFeed items={researchItems} emptyLabel="No Activity Yet" max={4} /><div className="mt-2 grid grid-cols-2 gap-1.5">{["Market Intelligence", "Competitive Intelligence", "Open Questions", "Opportunities"].map((label) => <MetricTile compact key={label} label={label} value={researchItems.some((item) => item.toLowerCase().includes(label.toLowerCase())) ? "Active" : "0"} tone={researchItems.some((item) => item.toLowerCase().includes(label.toLowerCase())) ? "good" : "muted"} />)}</div>
          </ExecutivePanel></div>

          <div id="knowledge-vault" className="xl:col-span-3"><ExecutivePanel eyebrow="Knowledge" title="Knowledge Vault" source="Obsidian Vault" updated={updated}>
            <div className="grid grid-cols-2 gap-2"><MetricTile compact label="Recently Modified Notes" value={knowledgeVaultItems.length} tone={knowledgeVaultItems.length ? "good" : "muted"} /><MetricTile compact label="Most Referenced Notes" value={asArray(dashboard.knowledgeVault?.referenced_documents).length} tone={asArray(dashboard.knowledgeVault?.referenced_documents).length ? "good" : "muted"} /><MetricTile compact label="Recent Decisions" value={asArray(dashboard.knowledgeVault?.recent_decisions).length} tone={asArray(dashboard.knowledgeVault?.recent_decisions).length ? "warn" : "good"} /><MetricTile compact label="Knowledge Health" value={`${dashboard.knowledgeVault?.knowledge_health ?? 0}%`} tone={(dashboard.knowledgeVault?.knowledge_health ?? 0) > 50 ? "good" : "muted"} /></div><div className="mt-2"><MiniBars values={asArray(dashboard.knowledgeVault?.vault_growth_trend).map((point) => Number(point.count || 0))} tone="good" /></div><div className="mt-2"><CompactFeed items={knowledgeVaultItems} emptyLabel="No Activity Yet" max={3} /></div>
          </ExecutivePanel></div>

          <div id="artist-management" className="xl:col-span-3"><ExecutivePanel eyebrow="Artist Management" title="Collector + Gallery Pipeline" source="Artist CRM" updated={updated}>
            <div className="grid grid-cols-2 gap-2">{["Collectors", "Gallery Outreach", "Inventory", "Active Collection", "Upcoming Events", "Revenue"].map((label) => <MetricTile compact key={label} label={label} value={dashboard.artistManagement.milestones.find((item) => item.label.toLowerCase().includes(label.toLowerCase()))?.value ?? 0} tone="muted" />)}</div><div className="mt-3"><CompactFeed items={[...dashboard.artistManagement.priorities, ...dashboard.artistManagement.nextActions]} emptyLabel="No Activity Yet" max={3} /></div>
          </ExecutivePanel></div>

          <div id="hermes-operations" className="xl:col-span-3"><ExecutivePanel eyebrow="Operations" title="Hermes Health Strip" source="Hermes Backend" updated={updated}>
            <OperationsHealthStrip cards={operationsCards} diagnostics={backendIntegrationItems} onDiagnostics={() => setActiveDrawer({ type: "diagnostics", items: backendIntegrationItems })} />
          </ExecutivePanel></div>
        </div>

      </div>
      <DashboardDrawerPanel drawer={activeDrawer} onClose={() => setActiveDrawer(null)} onCaptured={async () => { window.dispatchEvent(new CustomEvent("hermes:dashboard-refresh")); }} />
    </section>
  );
}

export default function ReportsPage() {
  const { setAfterTitle, setEnd, setTitle } = usePageHeader();
  const [dashboard, setDashboard] = useState<DashboardViewModel | null>(null);
  const [project] = useState("");
  const [query] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      try {
        const data = await api.getDashboardV2({ days: 7, project, q: query });
        setDashboard(buildDashboardV2(data, project, query));
      } catch (err) {
        if (!isMissingDashboardEndpoint(err)) throw err;
        const reports = await api.getReports({ project, q: query, limit: 50 });
        setDashboard(buildFallbackDashboard(reports));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setDashboard((current) => current ?? buildFallbackDashboard(createEmptyReports(project, query)));
    } finally {
      setLoading(false);
    }
  }, [project, query]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    const refresh = () => void load();
    window.addEventListener("hermes:dashboard-refresh", refresh);
    return () => window.removeEventListener("hermes:dashboard-refresh", refresh);
  }, [load]);

  useEffect(() => {
    setTitle("");
    setAfterTitle(null);
    setEnd(null);
    return () => {
      setTitle(null);
      setAfterTitle(null);
      setEnd(null);
    };
  }, [setAfterTitle, setEnd, setTitle]);

  return (
    <div className="-m-4 min-h-[calc(100vh-3rem)] w-[calc(100%+2rem)]">
      <div className="sr-only"><PluginSlot name="reports:top" /></div>

      {dashboard && <ExecutiveCommandCenterShell dashboard={dashboard} />}

      {loading && !dashboard && <LoadingCard label="Loading Hermes OS Executive Command Center…" />}

      {error && (
        <Card>
          <CardContent className="py-6 text-center text-sm text-destructive">
            Dashboard data failed to load: {error}
          </CardContent>
        </Card>
      )}
      <div className="sr-only"><PluginSlot name="reports:bottom" /></div>
    </div>
  );
}

