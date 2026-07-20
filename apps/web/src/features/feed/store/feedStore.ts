// Re-export the root feed store so features/feed/* can import from a single
// path. All state and actions live in @/store/feedStore — this is a thin
// barrel to match the architecture layout spec.
export { useFeedStore } from "@/store/feedStore";
