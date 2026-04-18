import { redirect } from 'next/navigation'

// Legacy /training route — consolidated into Knowledge
export default function TrainingRedirect() {
  redirect('/knowledge')
}
