/**
 * What the modal slot renders when no overlay route is matched: nothing.
 *
 * Required, not optional. Without a `default.tsx` a hard navigation to a route with no
 * interceptor makes Next fail to match the slot, and the whole layout 404s.
 */
export default function Default() {
  return null;
}
