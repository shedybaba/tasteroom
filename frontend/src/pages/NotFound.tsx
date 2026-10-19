import { Link } from 'react-router-dom'
import { Button, ErrorState } from '../components/ui'

export default function NotFound() {
  return <ErrorState title="Page not found" message="That page doesn’t exist." action={<Link to="/"><Button>Back to the examples</Button></Link>} />
}
