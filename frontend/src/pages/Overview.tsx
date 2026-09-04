import { AppLayout } from '@/components/layout/AppLayout'
import { AtRiskCustomersTable } from '@/components/widgets/AtRiskCustomersTable'
import { CustomerSegmentsChart } from '@/components/widgets/CustomerSegmentsChart'
import { DecisionPanel } from '@/components/widgets/DecisionPanel'
import { EnterpriseTrendChart } from '@/components/widgets/EnterpriseTrendChart'
import { KpiRow } from '@/components/widgets/KpiRow'
import { ProjectRiskWidget } from '@/components/widgets/ProjectRiskWidget'
import { RevenueByRegionChart } from '@/components/widgets/RevenueByRegionChart'
import { SupportHealthWidget } from '@/components/widgets/SupportHealthWidget'

export function Overview() {
  return (
    <AppLayout title="Overview" subtitle="Enterprise-wide performance and decision intelligence">
      <div className="space-y-6">
        <KpiRow />

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <EnterpriseTrendChart />
          </div>
          <CustomerSegmentsChart />
        </div>

        <DecisionPanel />

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <RevenueByRegionChart />
          <ProjectRiskWidget />
          <SupportHealthWidget />
        </div>

        <AtRiskCustomersTable />
      </div>
    </AppLayout>
  )
}
