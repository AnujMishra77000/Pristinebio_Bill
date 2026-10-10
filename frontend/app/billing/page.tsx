"use client";

import { AppShell } from "@/app/components/AppShell";
import { AuthGate } from "@/app/components/AuthGate";
import { BillingDocumentActions } from "@/app/components/BillingDocumentActions";
import { PageHeader } from "@/app/components/PageHeader";

export default function BillingPage() {
  return (
    <AuthGate>
      <AppShell>
        <div className="workspace-page">
          <PageHeader icon="billing" eyebrow="Billing desk" title="Create a bill" description="Choose a document type to open its dedicated bill-creation page." />

          <BillingDocumentActions />
        </div>
      </AppShell>
    </AuthGate>
  );
}
