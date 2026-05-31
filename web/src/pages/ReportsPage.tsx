import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  ExternalLink,
  FileText,
  GitBranch,
  RefreshCw,
  Search,
  Server,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  DeploymentStatusSummary,
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

function formatDate(value?: number | null): string {
  if (!value) return "—";
  return new Date(value * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusTone(status: string): string {
  switch (status.toLowerCase()) {
    case "healthy":
    case "done":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-600";
    case "degraded":
    case "review":
    case "blocked":
      return "border-amber-500/30 bg-amber-500/10 text-amber-600";
    case "failed":
      return "border-destructive/30 bg-destructive/10 text-destructive";
    default:
      return "border-border bg-secondary/40 text-muted-foreground";
  }
}

function EmptyState({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center text-muted-foreground">
      <ClipboardList className="mb-3 h-8 w-8 opacity-40" />
      <p className="text-sm font-medium text-foreground">{label}</p>
      <p className="mt-1 max-w-md text-xs text-text-tertiary">{detail}</p>
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
              <a href={`/tasks/${task.id}`} className="truncate text-sm font-medium text-foreground hover:underline">
                {task.title}
              </a>
              {task.status && <Badge className={statusTone(task.status)}>{task.status}</Badge>}
            </div>
            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{task.summary || "No summary provided."}</p>
            <p className="mt-1 font-mono text-xs text-text-tertiary">{task.id} · {task.project}</p>
          </div>
          <div className="shrink-0 text-left text-xs text-text-tertiary sm:text-right">
            <div>{task.assignee || "unassigned"}</div>
            <div>{formatDate(task.completed_at ?? task.created_at)}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ReportList({ reports, emptyLabel }: { reports: ReportFileSummary[]; emptyLabel: string }) {
  if (reports.length === 0) {
    return <EmptyState label={emptyLabel} detail="Report files are read automatically from Hermes report directories." />;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {reports.map((report) => (
        <Card key={report.id} className="bg-card/70">
          <CardContent className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="truncate text-sm font-medium text-foreground">{report.title}</h3>
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
              <h3 className="truncate text-sm font-medium text-foreground">{project.project}</h3>
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
  const { setAfterTitle, setEnd } = usePageHeader();
  const [data, setData] = useState<ReportsResponse | null>(null);
  const [project, setProject] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.getReports({ project, q: query, limit: 50 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [project, query]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setAfterTitle(
      <span className="hidden font-mondwest text-xs normal-case text-muted-foreground sm:inline">
        Executive reports
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
    const summary = data?.summary;
    return [
      { label: "Completed tasks", value: String(summary?.completed_tasks ?? 0), icon: <CheckCircle2 className="h-4 w-4" /> },
      { label: "Review required", value: String(summary?.review_required ?? 0), icon: <AlertTriangle className="h-4 w-4" /> },
      { label: "Active projects", value: String(summary?.active_projects ?? 0), icon: <ClipboardList className="h-4 w-4" /> },
      { label: "Report files", value: String((summary?.completion_reports ?? 0) + (summary?.qa_findings ?? 0)), icon: <FileText className="h-4 w-4" /> },
      { label: "Deployments", value: String(summary?.deployment_updates ?? 0), icon: <Server className="h-4 w-4" /> },
      { label: "GitHub updates", value: String(summary?.github_updates ?? 0), icon: <GitBranch className="h-4 w-4" /> },
    ];
  }, [data]);

  const isEmpty = data &&
    data.recent_completed.length === 0 &&
    data.review_required.length === 0 &&
    data.active_projects.length === 0 &&
    data.completion_reports.length === 0 &&
    data.qa_findings.length === 0 &&
    data.deployment_status.length === 0 &&
    data.github_activity.length === 0;

  return (
    <div className="flex flex-col gap-6">
      <PluginSlot name="reports:top" />

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

      {loading && !data && (
        <div className="flex items-center justify-center py-24">
          <Spinner className="text-2xl text-primary" />
        </div>
      )}

      {error && (
        <Card>
          <CardContent className="py-6 text-center text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

      {data && (
        <>
          <Card>
            <CardContent className="py-6">
              <Stats items={statItems} />
            </CardContent>
          </Card>

          {isEmpty && (
            <Card>
              <CardContent>
                <EmptyState
                  label="No reports matched"
                  detail="Try removing filters, completing kanban tasks, or adding markdown report files under Hermes reports directories."
                />
              </CardContent>
            </Card>
          )}

          <section className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <CheckCircle2 className="h-5 w-5 text-emerald-500" /> Recent completed tasks
                </CardTitle>
              </CardHeader>
              <CardContent>
                <TaskList tasks={data.recent_completed} emptyLabel="No completed tasks" />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <AlertTriangle className="h-5 w-5 text-amber-500" /> Review required
                </CardTitle>
              </CardHeader>
              <CardContent>
                <TaskList tasks={data.review_required} emptyLabel="No review queue" />
              </CardContent>
            </Card>
          </section>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <ClipboardList className="h-5 w-5 text-muted-foreground" /> Active projects
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ProjectList projects={data.active_projects} />
            </CardContent>
          </Card>

          <section className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <FileText className="h-5 w-5 text-muted-foreground" /> Completion reports
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ReportList reports={data.completion_reports} emptyLabel="No completion report files" />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <AlertTriangle className="h-5 w-5 text-muted-foreground" /> QA findings
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ReportList reports={data.qa_findings} emptyLabel="No QA findings" />
              </CardContent>
            </Card>
          </section>

          <section className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Server className="h-5 w-5 text-muted-foreground" /> Deployment status
                </CardTitle>
              </CardHeader>
              <CardContent>
                <DeploymentList items={data.deployment_status} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <GitBranch className="h-5 w-5 text-muted-foreground" /> GitHub activity
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ReportList reports={data.github_activity} emptyLabel="No GitHub activity reports" />
              </CardContent>
            </Card>
          </section>

          <p className="flex items-center gap-1 text-xs text-text-tertiary">
            <ExternalLink className="h-3.5 w-3.5" /> Generated {formatDate(data.generated_at)} from kanban task state and local report files.
          </p>
        </>
      )}
      <PluginSlot name="reports:bottom" />
    </div>
  );
}
