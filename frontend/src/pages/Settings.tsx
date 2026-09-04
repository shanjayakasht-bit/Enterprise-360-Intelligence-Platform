import { AppLayout } from '@/components/layout/AppLayout'
import { SectionCard, DataRow } from '@/components/ui/SectionCard'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string

export function Settings() {
  return (
    <AppLayout title="Settings" subtitle="Environment and connection information">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <SectionCard title="API Connection">
          <DataRow label="API Base URL" value={API_BASE_URL} />
          <DataRow label="Data Source" value="NEXORA FastAPI backend" />
        </SectionCard>
      </div>
    </AppLayout>
  )
}
