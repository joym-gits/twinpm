"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { SettingsShell } from "@/components/settings/settings-nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, ApiError, unwrap, type Schemas } from "@/lib/api/client";
import { useMe } from "@/lib/auth/use-me";
import { relTime } from "@/lib/format";

type Role = Schemas["UserOut"]["role"];
const ROLES: { value: Role; label: string }[] = [
  { value: "org_admin", label: "Org admin" },
  { value: "tpm", label: "TPM" },
  { value: "eng_manager", label: "Eng manager" },
  { value: "executive", label: "Executive" },
  { value: "member", label: "Member" },
  { value: "viewer", label: "Viewer" },
];
const ROLE_VALUES = ROLES.map((r) => r.value) as [Role, ...Role[]];

const schema = z.object({
  name: z.string().trim().min(1, "Enter a name").max(200),
  email: z.email("Enter a valid email"),
  role: z.enum(ROLE_VALUES),
  password: z.string().min(12, "At least 12 characters").max(256),
});
type Values = z.infer<typeof schema>;

function AddMemberDialog({ open, setOpen }: { open: boolean; setOpen: (o: boolean) => void }) {
  const qc = useQueryClient();
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name: "", email: "", role: "member", password: "" } });
  const create = useMutation({
    mutationFn: async (v: Values) => unwrap(await api.POST("/api/v1/members", { body: v })),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["members"] });
      form.reset();
      setOpen(false);
    },
  });
  const e = form.formState.errors;
  const field = (id: keyof Values, label: string, input: React.ReactNode) => (
    <div className="space-y-1">
      <Label htmlFor={`m-${id}`}>{label}</Label>
      {input}
      {e[id] && (
        <p id={`m-${id}-err`} className="text-xs text-danger">
          {e[id]?.message}
        </p>
      )}
    </div>
  );
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent title="Add member" description="They can sign in with this email and password, and change the password later.">
        <form className="space-y-3" noValidate onSubmit={form.handleSubmit((v) => create.mutate(v))}>
          {field("name", "Name", <Input id="m-name" aria-invalid={!!e.name} aria-describedby="m-name-err" {...form.register("name")} />)}
          {field("email", "Email", <Input id="m-email" type="email" autoComplete="off" aria-invalid={!!e.email} aria-describedby="m-email-err" {...form.register("email")} />)}
          {field(
            "role",
            "Role",
            <Select id="m-role" className="w-full" {...form.register("role")}>
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </Select>,
          )}
          {field(
            "password",
            "Initial password",
            <Input id="m-password" type="password" autoComplete="new-password" aria-invalid={!!e.password} aria-describedby="m-password-err" {...form.register("password")} />,
          )}
          {create.isError && (
            <p role="alert" className="text-sm text-danger">
              {create.error instanceof ApiError ? create.error.message : "Couldn't add member."}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="accent" disabled={create.isPending}>
              {create.isPending ? "Adding…" : "Add member"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function MemberRow({ u, self }: { u: Schemas["UserOut"]; self: boolean }) {
  const qc = useQueryClient();
  const update = useMutation({
    mutationFn: async (body: Schemas["MemberUpdate"]) => unwrap(await api.PATCH("/api/v1/members/{user_id}", { params: { path: { user_id: u.id } }, body })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["members"] }),
  });
  return (
    <TR>
      <TD>
        <p className="font-medium">
          {u.name} {self && <span className="text-xs text-muted">(you)</span>}
        </p>
        <p className="text-xs text-muted">{u.email}</p>
        {update.isError && (
          <p role="alert" className="text-xs text-danger">
            {update.error instanceof ApiError ? update.error.message : "Update failed."}
          </p>
        )}
      </TD>
      <TD>
        <Select aria-label={`Role for ${u.name}`} value={u.role} disabled={self || update.isPending} onChange={(e) => update.mutate({ role: e.target.value as Role })}>
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </Select>
      </TD>
      <TD>
        <Badge tone={u.is_active ? "success" : "neutral"}>{u.is_active ? "Active" : "Deactivated"}</Badge>
      </TD>
      <TD className="text-xs text-muted">{u.last_login_at ? relTime(u.last_login_at) : "Never"}</TD>
      <TD>
        {!self && (
          <Button size="sm" variant="outline" disabled={update.isPending} onClick={() => update.mutate({ is_active: !u.is_active })}>
            {u.is_active ? "Deactivate" : "Reactivate"}
          </Button>
        )}
      </TD>
    </TR>
  );
}

export default function MembersPage() {
  const me = useMe();
  const isAdmin = me.data?.permissions.includes("members:manage") ?? false;
  const [adding, setAdding] = useState(false);
  const q = useQuery({ queryKey: ["members"], enabled: isAdmin, queryFn: async () => unwrap(await api.GET("/api/v1/members")) });
  return (
    <SettingsShell title="Members & roles" description="Who can use TwinPM in this organisation, and what they can do." admin>
      <div className="flex justify-end">
        <Button size="sm" variant="accent" onClick={() => setAdding(true)}>
          <UserPlus /> Add member
        </Button>
      </div>
      <Card className="px-2">
        {q.isLoading && <SkeletonLoader rows={5} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data?.length === 0 && <EmptyState title="No members yet" />}
        {!!q.data?.length && (
          <Table aria-label="Members" data-testid="members-table">
            <THead>
              <TR>
                <TH>Member</TH>
                <TH>Role</TH>
                <TH>Status</TH>
                <TH>Last sign-in</TH>
                <TH>
                  <span className="sr-only">Actions</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {q.data.map((u) => (
                <MemberRow key={u.id} u={u} self={u.id === me.data?.user.id} />
              ))}
            </TBody>
          </Table>
        )}
      </Card>
      <AddMemberDialog open={adding} setOpen={setAdding} />
    </SettingsShell>
  );
}
