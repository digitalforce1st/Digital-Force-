import { redirect } from 'next/navigation'

// Legacy /media route — consolidated into Knowledge
export default function MediaRedirect() {
  redirect('/knowledge')
}
