import { SourceDetail } from "@/components/saga/source-detail";

/** /sources/{id} opened cold. From inside the app it renders as an overlay — see @modal. */
export default async function SourceDetailPage({
  params
}: {
  params: Promise<{ sourceId: string }>;
}) {
  const { sourceId } = await params;
  return (
    <div className="h-full overflow-y-auto">
      <SourceDetail sourceId={sourceId} />
    </div>
  );
}
