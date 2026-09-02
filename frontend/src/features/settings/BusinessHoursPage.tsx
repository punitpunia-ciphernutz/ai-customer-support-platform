import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import type { BusinessHoursConfig, BusinessHoursScheduleItem } from "@/types";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export function BusinessHoursPage() {
  const qc = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["business-hours"],
    queryFn: () => api<BusinessHoursConfig[]>("/business-hours"),
  });

  const bh = data?.[0];
  const [timezone, setTimezone] = useState("UTC");
  const [schedule, setSchedule] = useState<BusinessHoursScheduleItem[]>([]);
  const [holidayDate, setHolidayDate] = useState("");
  const [holidayName, setHolidayName] = useState("");

  useEffect(() => {
    if (bh) {
      setTimezone(bh.timezone);
      setSchedule(bh.schedule);
    } else {
      setSchedule(DAYS.map((_, i) => ({ day_of_week: i, closed: i >= 5, open_time: "09:00", close_time: "18:00" })));
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
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["business-hours"] }),
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
  });

  const removeHoliday = useMutation({
    mutationFn: (holidayId: string) =>
      api(`/business-hours/${bh!.id}/holidays/${holidayId}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["business-hours"] }),
  });

  if (isLoading) return <LoadingState message="Loading business hours…" />;
  if (isError) return <Alert type="error">{error instanceof ApiError ? error.message : "Failed to load."}</Alert>;

  const updateScheduleRow = (day: number, patch: Partial<BusinessHoursScheduleItem>) => {
    setSchedule((rows) => rows.map((row) => (row.day_of_week === day ? { ...row, ...patch } : row)));
  };

  return (
    <div className="page">
      <PageHeader title="Business Hours" description="Support operating hours, timezone, and holidays." />
      <div className="card stack gap-md">
        <label>
          Timezone
          <input className="input" value={timezone} onChange={(e) => setTimezone(e.target.value)} />
        </label>
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
                    className="input"
                    disabled={row.closed}
                    value={row.closed ? "" : row.open_time ?? ""}
                    onChange={(e) => updateScheduleRow(row.day_of_week, { open_time: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    className="input"
                    disabled={row.closed}
                    value={row.closed ? "" : row.close_time ?? ""}
                    onChange={(e) => updateScheduleRow(row.day_of_week, { close_time: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={row.closed}
                    onChange={(e) => updateScheduleRow(row.day_of_week, { closed: e.target.checked })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button type="button" className="btn btn-primary" onClick={() => void save.mutate({ timezone, schedule })}>
          Save schedule
        </button>
      </div>
      {bh && (
        <div className="card stack gap-md">
          <h3>Holidays</h3>
          <ul>
            {(bh.holidays ?? []).map((h) => (
              <li key={h.id ?? `${h.date}-${h.name}`}>
                {h.date} — {h.name}{" "}
                {h.id && (
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => removeHoliday.mutate(h.id!)}>
                    Remove
                  </button>
                )}
              </li>
            ))}
          </ul>
          <div className="row gap-sm">
            <input className="input" type="date" value={holidayDate} onChange={(e) => setHolidayDate(e.target.value)} />
            <input
              className="input"
              placeholder="Holiday name"
              value={holidayName}
              onChange={(e) => setHolidayName(e.target.value)}
            />
            <button
              type="button"
              className="btn btn-secondary"
              disabled={!holidayDate || !holidayName}
              onClick={() => void addHoliday.mutate()}
            >
              Add holiday
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
