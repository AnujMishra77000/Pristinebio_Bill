"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { AuthFlow } from "@/app/components/AuthFlow";
import { AuthLayout } from "@/app/components/AuthLayout";

export default function RegisterPage() {
  const router = useRouter();
  return (
    <AuthLayout eyebrow="Admin registration" title="Create an Admin account" description="Register an active Admin account. Multiple Admin registrations are currently allowed." footer={<Link href="/login" className="rounded font-semibold text-peacock underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-peacock">← Back to sign in</Link>}>
      <AuthFlow initialMode="register" onComplete={() => router.push("/")} />
    </AuthLayout>
  );
}
