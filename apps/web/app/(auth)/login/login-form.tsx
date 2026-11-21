"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { api, ApiError, unwrap } from "@/lib/api/client";

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Enter your password"),
});
type FormValues = z.infer<typeof schema>;

const ROLE_LABEL: Record<string, string> = {
  org_admin: "Org admin",
  tpm: "TPM",
  eng_manager: "Eng manager",
  executive: "Executive",
  member: "Member",
  viewer: "Viewer",
};

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });
  const demoUsers = useQuery({
    queryKey: ["demo-users"],
    queryFn: async () => unwrap(await api.GET("/api/v1/auth/demo-users")),
  });

  async function onSubmit(values: FormValues) {
    setError(null);
    try {
      const session = unwrap(await api.POST("/api/v1/auth/login", { body: values }));
      const next = params.get("next");
      router.replace(next && next.startsWith(`/${session.org_slug}/`) ? next : `/${session.org_slug}/command-center`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Sign-in failed. Try again.");
    }
  }

  return (
    <div className="w-full max-w-sm space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="mt-1 text-sm text-muted">Welcome back to your program&apos;s twin.</p>
      </div>
      <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)} noValidate>
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            aria-invalid={!!form.formState.errors.email}
            {...form.register("email")}
          />
          {form.formState.errors.email && (
            <p className="text-xs text-danger" role="alert">{form.formState.errors.email.message}</p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            aria-invalid={!!form.formState.errors.password}
            {...form.register("password")}
          />
          {form.formState.errors.password && (
            <p className="text-xs text-danger" role="alert">{form.formState.errors.password.message}</p>
          )}
        </div>
        {error && (
          <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      {demoUsers.data && demoUsers.data.length > 0 && (
        <Card className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-semibold">Demo users</p>
            <Badge tone="accent">Demo mode</Badge>
          </div>
          <ul className="space-y-1">
            {demoUsers.data.map((u) => (
              <li key={u.email}>
                <button
                  type="button"
                  className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-2"
                  onClick={() => form.setValue("email", u.email, { shouldValidate: true })}
                >
                  <span>{u.name}</span>
                  <span className="text-xs text-muted">{ROLE_LABEL[u.role] ?? u.role}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-muted">Password is the SEED_DEMO_PASSWORD from your .env.</p>
        </Card>
      )}
    </div>
  );
}
