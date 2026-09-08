export { cn } from "./cn";

export {
  Button,
  ButtonAnchor,
  ButtonLink,
  buttonClass,
  type ButtonSize,
  type ButtonVariant
} from "./primitives/button";
export {
  Divider,
  Field,
  Input,
  Label,
  Panel,
  Pill,
  Textarea,
  type PillTone
} from "./primitives/bits";
export { ProgressBar, SourceIcon, StatusBadge, sourceIcons } from "./primitives/source";
export { EmptyState, Skeleton } from "./primitives/feedback";
// `Prose` is deliberately NOT re-exported here. It carries a markdown parser, and this
// barrel is imported by every route - including /login, which has no answers to render.
// Import it from "@kb/ui/markdown" instead.
export { Logo } from "./primitives/logo";
export { ConfirmDialog } from "./primitives/confirm-dialog";
export {
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  type ModalPlacement,
  type ModalSize
} from "./primitives/modal";
export { THEME_SCRIPT, THEME_STORAGE_KEY, useTheme, type Theme } from "./use-theme";
