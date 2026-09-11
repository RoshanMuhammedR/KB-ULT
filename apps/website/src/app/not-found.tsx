import { Navbar } from "@/components/chrome/navbar";
import { Button } from "@/components/ui/button";
import { InteractiveGrid } from "@/components/ui/interactive-grid";

export default function NotFound() {
  return (
    <>
      <Navbar />
      <main className="not-found">
        <InteractiveGrid />
        <div className="not-found__content">
          <p className="t-3xl not-found__index" aria-hidden="true">
            404
          </p>
          <h1 className="t-xl">Page not found</h1>
          <p className="t-md not-found__text">
            The link may be out of date. Everything Saga does lives on one page — start there.
          </p>
          <Button label="Go home" href="/" />
        </div>
      </main>
    </>
  );
}
