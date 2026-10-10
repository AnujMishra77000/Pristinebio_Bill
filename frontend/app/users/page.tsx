"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { AppShell } from "@/app/components/AppShell";
import { AuthGateStatus, useAuthStatus, useSessionState } from "@/app/components/AuthGate";
import { SecurityError, SecurityField, SecuritySection, errorMessage, securityButton } from "@/app/components/SecurityForms";
import { PageHeader } from "@/app/components/PageHeader";
import { apiRequest, validateSession } from "@/app/lib/api";
import type { AuthAuditEvent, Branch, CreatedInvitation, Invitation, User, UserRole } from "@/app/lib/types";

type UserEdit = Pick<User, "email" | "full_name" | "role" | "branch_ids" | "is_active">;
const blankInvite = { email: "", role: "staff" as UserRole, branch_ids: [] as number[] };
function toggle(ids: number[], id: number) { return ids.includes(id) ? ids.filter(value => value !== id) : [...ids, id]; }
function RoleField({ value, onChange, label = "Role" }: { value: UserRole; onChange: (role: UserRole) => void; label?: string }) {
  return <label className="block text-sm font-medium text-slate-600">{label}<select className="mt-1.5 w-full rounded-xl border border-slate-300 p-2.5" value={value} onChange={event => onChange(event.target.value as UserRole)}><option value="staff">Staff</option><option value="manager">Manager</option><option value="admin">Admin</option></select></label>;
}
function Assignments({ profiles, ids, onChange }: { profiles: Branch[]; ids: number[]; onChange: (ids: number[]) => void }) {
  return <fieldset className="space-y-2"><legend className="mb-2 text-sm font-medium">Allowed Seller/GST profiles</legend>{profiles.map(profile => <label key={profile.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={ids.includes(profile.id)} onChange={() => onChange(toggle(ids, profile.id))} />{profile.name} · {profile.gstin}</label>)}{!profiles.length && <p className="text-sm text-slate-500">No Seller/GST profiles are available.</p>}</fieldset>;
}

export default function UsersPage() {
  const status = useAuthStatus();
  const { session } = useSessionState();
  const admin = session?.user.role === "admin";
  const [users, setUsers] = useState<User[]>([]);
  const [profiles, setProfiles] = useState<Branch[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [audit, setAudit] = useState<AuthAuditEvent[]>([]);
  const [invite, setInvite] = useState(blankInvite);
  const [link, setLink] = useState<string | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [edit, setEdit] = useState<UserEdit | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(async () => {
    const results = await Promise.allSettled([apiRequest<User[]>("/users"), apiRequest<Branch[]>("/branches"), apiRequest<Invitation[]>("/auth/invitations"), apiRequest<AuthAuditEvent[]>("/auth/audit")]);
    const [loadedUsers, loadedProfiles, loadedInvitations, loadedAudit] = results;
    if (loadedUsers.status === "fulfilled") setUsers(loadedUsers.value);
    if (loadedProfiles.status === "fulfilled") setProfiles(loadedProfiles.value);
    if (loadedInvitations.status === "fulfilled") setInvitations(loadedInvitations.value);
    if (loadedAudit.status === "fulfilled") setAudit(loadedAudit.value);
    const errors = results.filter(result => result.status === "rejected").map(result => errorMessage(result.reason));
    if (errors.length) setError(errors.join("; "));
  }, []);
  useEffect(() => { if (status === "authenticated" && admin) void load(); }, [status, admin, load]);
  async function action(operation: () => Promise<void>) {
    setBusy(true); setError(null); setMessage(null);
    try { await operation(); await load(); }
    catch (requestError) { setError(errorMessage(requestError)); }
    finally { setBusy(false); }
  }
  function createInvitation(event: FormEvent) {
    event.preventDefault();
    void action(async () => {
      const result = await apiRequest<CreatedInvitation>("/auth/invitations", { method: "POST", body: JSON.stringify(invite) });
      setLink(window.location.origin + "/login#invite=" + encodeURIComponent(result.token));
      setInvite(blankInvite); setMessage("Invitation created. Deliver the one-time link manually.");
    });
  }
  function editUser(user: User) { setEditId(user.id); setEdit({ email: user.email, full_name: user.full_name, role: user.role, branch_ids: [...user.branch_ids], is_active: user.is_active }); }
  function saveUser(event: FormEvent) {
    event.preventDefault();
    if (!edit || editId === null) return;
    void action(async () => {
      await apiRequest("/users/" + editId, { method: "PATCH", body: JSON.stringify(edit) });
      setEdit(null); setEditId(null); setMessage("User updated.");
      if (editId === session?.user.id) await validateSession();
    });
  }
  return <AuthGateStatus status={status}><AppShell><div className="workspace-page"><PageHeader icon="users" eyebrow="Administration" title="Users & access" description="Invite people, review roles, and manage access to seller profiles." />{!admin ? <p>Only Admins can manage users, invitations and security audit events.</p> : <><SecurityError message={error} />{message && <p role="status">{message}</p>}<div className="grid gap-6 md:grid-cols-2"><SecuritySection title="Invite a user"><form className="space-y-4" onSubmit={createInvitation}><SecurityField label="Invitation email" value={invite.email} type="email" onChange={email => setInvite(current => ({ ...current, email }))} /><RoleField label="Invitation role" value={invite.role} onChange={role => setInvite(current => ({ ...current, role }))} /><Assignments profiles={profiles} ids={invite.branch_ids} onChange={branch_ids => setInvite(current => ({ ...current, branch_ids }))} /><p className="text-sm text-slate-500">The recipient chooses their own passphrase. Deliver the invitation link manually.</p><button type="submit" className={securityButton} disabled={busy}>Create invitation</button></form>{link && <div className="space-y-3"><label className="block text-sm">One-time invitation link<input className="mt-2 w-full rounded-xl border border-slate-300 p-2 text-xs" readOnly value={link} /></label><p className="text-sm text-slate-500">Shown once here. Copy it before dismissing or leaving this page.</p><button type="button" onClick={() => setLink(null)} className={securityButton}>Dismiss invitation link</button></div>}</SecuritySection><SecuritySection title="Invitations"><ul className="space-y-4">{invitations.map(item => <li key={item.id} className="space-y-2 rounded-xl border border-slate-200 p-3"><p className="text-sm font-semibold">{item.email} · {item.role}</p><p className="text-xs text-slate-500">Expires {item.expires_at} · {item.revoked_at ? "Revoked" : item.accepted_at ? "Accepted" : "Pending"} · Profiles {item.branch_ids.join(", ") || "None"}</p>{!item.accepted_at && !item.revoked_at && <button type="button" className={securityButton} disabled={busy} aria-label={"Revoke invitation " + item.id} onClick={() => void action(async () => { await apiRequest("/auth/invitations/" + item.id, { method: "DELETE" }); setMessage("Invitation revoked."); })}>Revoke invitation</button>}</li>)}</ul></SecuritySection></div><SecuritySection title="User access"><ul className="space-y-4">{users.map(user => <li key={user.id} className="space-y-3 rounded-xl border border-slate-200 p-4"><p className="font-semibold">{user.full_name} · {user.email}</p><p className="text-sm text-slate-500">{user.role} · {user.is_active ? "Active" : "Inactive"} · Profiles {user.branch_ids.join(", ") || "None"}</p><div className="flex flex-wrap gap-2"><button type="button" disabled={busy} className={securityButton} aria-label={"Edit " + user.full_name} onClick={() => editUser(user)}>Edit access</button><button type="button" disabled={busy} className={securityButton} aria-label={"Revoke sessions for " + user.full_name} onClick={() => void action(async () => { await apiRequest("/users/" + user.id + "/revoke-sessions", { method: "POST" }); setMessage("User sessions revoked."); if (user.id === session?.user.id) await validateSession(); })}>Revoke sessions</button></div></li>)}</ul></SecuritySection>{edit && <SecuritySection title="Edit user"><form onSubmit={saveUser} className="space-y-4"><SecurityField label="Full name" value={edit.full_name} onChange={full_name => setEdit(current => current && ({ ...current, full_name }))} /><SecurityField label="Email" type="email" value={edit.email} onChange={email => setEdit(current => current && ({ ...current, email }))} /><RoleField value={edit.role} onChange={role => setEdit(current => current && ({ ...current, role }))} /><Assignments profiles={profiles} ids={edit.branch_ids} onChange={branch_ids => setEdit(current => current && ({ ...current, branch_ids }))} /><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.is_active} onChange={event => setEdit(current => current && ({ ...current, is_active: event.target.checked }))} />Active</label><div className="flex gap-3"><button type="submit" disabled={busy} className={securityButton}>Save user</button><button type="button" onClick={() => { setEdit(null); setEditId(null); }}>Cancel edit</button></div></form></SecuritySection>}<SecuritySection title="Security audit (latest 100)"><ul className="space-y-4">{audit.map(event => <li key={event.id} className="space-y-2 rounded-xl border border-slate-200 p-3"><p className="text-sm font-semibold">{event.action}</p><p className="text-xs text-slate-500">{event.created_at} · Actor {event.actor_id ?? "System"} · {event.entity_type} {event.entity_id}</p><details><summary className="text-sm">Before / after</summary><pre className="overflow-x-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify({ before: event.before, after: event.after }, null, 2)}</pre></details></li>)}</ul></SecuritySection></>}</div></AppShell></AuthGateStatus>;
}
