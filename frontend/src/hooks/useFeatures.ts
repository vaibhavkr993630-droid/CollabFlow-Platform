import { useQuery } from '@tanstack/react-query'

import { getFeatures } from '../api/features'

/** Which optional features are on. Treated as off until the server says otherwise. */
export function useFeatures() {
  const query = useQuery({
    queryKey: ['features'],
    queryFn: getFeatures,
    // A server setting: it only changes on restart, so one fetch per session is enough.
    staleTime: Infinity,
  })
  return { assistant: query.data?.assistant ?? false }
}
