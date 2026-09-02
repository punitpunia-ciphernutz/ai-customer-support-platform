import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import { SettingsSubNav } from "@/components/shared/SettingsSubNav";
import type { BusinessHoursConfig, BusinessHoursScheduleItem } from "@/types";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const DEFAULT_SCHEDULE = (): BusinessHoursScheduleItem[] =>
  DAYS.map((_, i) => ({
    day_of_week: i,
    closed: i >= 5,
    open_time: "09:00",
    close_time: "18:00",
  }));

export function BusinessHoursPage() {
  const qc = useQueryClient();
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["business-hours"],
    queryFn: () => api<BusinessHoursConfig[]>("/business-hours"),
  });

  const bh = data?.[0];
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [schedule, setSchedule] = useState<BusinessHoursScheduleItem[]>(DEFAULT_SCHEDULE());
  const [holidayDate, setHolidayDate] = useState("");
  const [holidayName, setHolidayName] = useState("");

  useEffect(() => {
    if (bh) {
      setTimezone(bh.timezone);
      setSchedule(bh.schedule.length ? bh.schedule : DEFAULT_SCHEDULE());
    }
  }, [bh]);

  const save = useMutation({
    mutationFn: (body: Partial<BusinessHoursConfig>) =>
      bh
        ? api(`/business-hours/${bh.id}`, { method: "PATCH", body: JSON.stringify(body) })
        : api("/business-hours", {
            method: "POST",
            body: JSON.stringify({
              name: "Support Hours",
              timezone: body.timezone ?? "UTC",
              schedule: body.schedule ?? [],
            }),
          }),
    onSuccess: () => {
      setSaveMsg("Business hours saved.");
      setSaveErr(null);
      void qc.invalidateQueries({ queryKey: ["business-hours"] });
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to save business hours.");
      setSaveMsg(null);
    },
  });

  const addHoliday = useMutation({
    mutationFn: () =>
      api(`/business-hours/${bh!.id}/holidays`, {
        method: "POST",
        body: JSON.stringify({ date: holidayDate, name: holidayName }),
      }),
    onSuccess: () => {
      setHolidayDate("");
      setHolidayName("");
      void qc.invalidateQueries({ queryKey: ["business-hours"] });
    },
    onError: (e) => setSaveErr(e instanceof ApiError ? e.message : "Failed to add holiday."),
  });

  const removeHoliday = useMutation({
    mutationFn: (holidayId: string) =>
      api(`/business-hours/${bh!.id}/holidays/${holidayId}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["business-hours"] }),
    onError: (e) => setSaveErr(e instanceof ApiError ? e.message : "Failed to remove holiday."),
  });

  if (isLoading) return <LoadingState message="Loading business hours…" />;

  const updateScheduleRow = (day: number, patch: Partial<BusinessHoursScheduleItem>) => {
    setSchedule((rows) => rows.map((row) => (row.day_of_week === day ? { ...row, ...patch } : row)));
  };

  return (
    <div className="page-scroll">
      <PageHeader
        title="Settings"
        description="Configure support hours, timezone, and holidays for SLA and routing."
      />
      <SettingsSubNav />

      {isError && (
        <Alert type="error">{error instanceof ApiError ? error.message : "Failed to load business hours."}</Alert>
      )}
      {saveMsg && <Alert type="success">{saveMsg}</Alert>}
      {saveErr && <Alert type="error">{saveErr}</Alert>}

      <section className="card mb-6">
        <h2 className="section-title">Support Hours</h2>
        <p className="form-hint mb-4">
          Used by SLA timers, missed chat handling, and future routing rules. Times are evaluated in the selected timezone.
        </p>

        <div className="form-field" style={{ maxWidth: 320 }}>
          <label className="form-label" htmlFor="bh-timezone">
            Timezone
          </label>
          <input
            id="bh-timezone"
            className="form-input"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            placeholder="Asia/Kolkata"
          />
          <span className="form-hint">IANA timezone, e.g. Asia/Kolkata, America/New_York</span>
        </div>

        <div className="table-wrap mt-4">
          <table className="data-table">
            <thead>
              <tr>
                <th>Day</th>
                <th>Open</th>
                <th>Close</th>
                <th>Closed</th>
              </tr>
            </thead>
            <tbody>
              {schedule.map((row) => (
                <tr key={row.day_of_week}>
                  <td>{DAYS[row.day_of_week]}</td>
                  <td>
                    <input
                      className="form-input"
                      type="time"
                      disabled={row.closed}
                      value={row.closed ? "" : row.open_time ?? ""}
                      onChange={(e) => updateScheduleRow(row.day_of_week, { open_time: e.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      className="form-input"
                      type="time"
                      disabled={row.closed}
                      value={row.closed ? "" : row.close_time ?? ""}
                      onChange={(e) => updateScheduleRow(row.day_of_week, { close_time: e.target.value })}
                    />
                  </td>
                  <td>
                    <label className="flex items-center gap-2" style={{ cursor: "pointer" }}>
                      <input
                        type="checkbox"
                        checked={row.closed}
                        onChange={(e) => updateScheduleRow(row.day_of_week, { closed: e.target.checked })}
                      />
                      Closed
                    </label>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <button
          type="button"
          className="btn btn-primary mt-4"
          disabled={save.isPending}
          onClick={() => void save.mutate({ timezone, schedule })}
        >
          {save.isPending ? "Saving…" : "Save schedule"}
        </button>
      </section>

      <section className="card">
        <h2 className="section-title">Holidays</h2>
        <p className="form-hint mb-4">Support is closed on these dates regardless of the weekly schedule.</p>

        {!bh ? (
          <p className="form-hint">Save the schedule first to add holidays.</p>
        ) : (
          <>
            {(bh.holidays ?? []).length > 0 ? (
              <div className="table-wrap mb-4">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Name</th>
                      <th aria-label="Actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {(bh.holidays ?? []).map((h) => (
                      <tr key={h.id ?? `${h.date}-${h.name}`}>
                        <td>{h.date}</td>
                        <td>{h.name}</td>
                        <td>
                          {h.id && (
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              disabled={removeHoliday.isPending}
                              onClick={() => removeHoliday.mutate(h.id!)}
                            >
                              Remove
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="form-hint mb-4">No holidays configured.</p>
            )}

            <div className="grid-2" style={{ maxWidth: 560 }}>
              <div className="form-field">
                <label className="form-label" htmlFor="holiday-date">
                  Date
                </label>
                <input
                  id="holiday-date"
                  className="form-input"
                  type="date"
                  value={holidayDate}
                  onChange={(e) => setHolidayDate(e.target.value)}
                />
              </div>
              <div className="form-field">
                <label className="form-label" htmlFor="holiday-name">
                  Holiday name
                </label>
                <input
                  id="holiday-name"
                  className="form-input"
                  placeholder="Christmas"
                  value={holidayName}
                  onChange={(e) => setHolidayName(e.target.value)}
                />
              </div>
            </div>
            <button
              type="button"
              className="btn btn-secondary mt-2"
              disabled={!holidayDate || !holidayName || addHoliday.isPending}
              onClick={() => void addHoliday.mutate()}
            >
              Add holiday
            </button>
          </>
        )}
      </section>
    </div>
  );
}
