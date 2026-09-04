import { Route, Routes } from 'react-router-dom'
import { CustomerDetail } from '@/pages/CustomerDetail'
import { Customers } from '@/pages/Customers'
import { Decisions } from '@/pages/Decisions'
import { Finance } from '@/pages/Finance'
import { Overview } from '@/pages/Overview'
import { Predictions } from '@/pages/Predictions'
import { Projects } from '@/pages/Projects'
import { Revenue } from '@/pages/Revenue'
import { Settings } from '@/pages/Settings'
import { Support } from '@/pages/Support'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Overview />} />
      <Route path="/customers" element={<Customers />} />
      <Route path="/customers/:customerId" element={<CustomerDetail />} />
      <Route path="/revenue" element={<Revenue />} />
      <Route path="/projects" element={<Projects />} />
      <Route path="/finance" element={<Finance />} />
      <Route path="/support" element={<Support />} />
      <Route path="/predictions" element={<Predictions />} />
      <Route path="/decisions" element={<Decisions />} />
      <Route path="/settings" element={<Settings />} />
    </Routes>
  )
}
