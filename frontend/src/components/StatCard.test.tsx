import { render, screen } from '@testing-library/react'
import { TrendingUp } from 'lucide-react'
import StatCard from './StatCard'

describe('StatCard', () => {
  it('renders the title and value', () => {
    render(<StatCard title="Total Balance" value="$12,500" icon={TrendingUp} />)

    expect(screen.getByText('Total Balance')).toBeInTheDocument()
    expect(screen.getByText('$12,500')).toBeInTheDocument()
  })

  it('shows an upward trend with a positive percentage', () => {
    render(<StatCard title="Revenue" value="$1,000" icon={TrendingUp} trend={8} />)

    expect(screen.getByText(/▲/)).toBeInTheDocument()
    expect(screen.getByText(/8%/)).toBeInTheDocument()
  })

  it('omits the trend indicator when trend is not provided', () => {
    render(<StatCard title="Savings" value="$500" icon={TrendingUp} />)

    expect(screen.queryByText(/▲|▼/)).not.toBeInTheDocument()
  })
})
