import { Suspense } from "react";
import { LoginForm } from "./login-form";

export default function LoginPage() {
  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <section className="hidden flex-col justify-between bg-navy-900 p-12 text-navy-50 lg:flex">
        <div className="flex items-center gap-2">
          <div className="grid size-8 place-items-center rounded-lg bg-teal-700 font-bold" aria-hidden>
            T
          </div>
          <span className="text-lg font-semibold">TwinPM</span>
        </div>
        <blockquote className="max-w-md text-2xl font-medium leading-snug">
          TwinPM doesn&apos;t just answer questions about your program. It runs it the way you
          would, and shows its reasoning every time.
        </blockquote>
        <p className="text-sm text-navy-100/70">AI digital twin for technical program managers</p>
      </section>
      <section className="flex items-center justify-center p-6">
        <Suspense>
          <LoginForm />
        </Suspense>
      </section>
    </main>
  );
}
