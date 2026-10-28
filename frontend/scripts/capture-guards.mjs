export function assertCaptureReady(
  route,
  bodyText,
  { hasRenderedDocumentPage = false, requireRenderedDocumentPage = route === '/documents' } = {},
) {
  if (/Loading/i.test(bodyText)) {
    throw new Error(`Refusing to capture ${route} while loading text is visible`);
  }
  if (route === '/documents' && requireRenderedDocumentPage && !hasRenderedDocumentPage) {
    throw new Error('Refusing to capture /documents before the PDF preview has rendered');
  }
}
