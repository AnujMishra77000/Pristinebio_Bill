"use client";

import { useRouter } from "next/navigation";
import { AuthFlow } from "@/app/components/AuthFlow";
import { AuthLayout } from "@/app/components/AuthLayout";

export default function LoginPage() {
  const router = useRouter();
  return (
    <AuthLayout eyebrow="Welcome back" title="Pristine Bio Billing" description="Sign in to your billing workspace or create an Admin account." footer={<p>Staff and Manager accounts are created through a private invitation from an Admin. Use the same sign-in form after accepting an invitation.</p>}>
      <AuthFlow onComplete={() => router.push("/")} />
    </AuthLayout>
  );
}
