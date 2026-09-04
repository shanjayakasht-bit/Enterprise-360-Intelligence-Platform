import { FilterProvider } from '@/context/FilterContext'
import { AppRoutes } from './router'

function App() {
  return (
    <FilterProvider>
      <AppRoutes />
    </FilterProvider>
  )
}

export default App
