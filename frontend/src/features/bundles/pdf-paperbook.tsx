'use client';

import { useEffect, useRef, useState } from 'react';
import * as pdfjs from 'pdfjs-dist/legacy/build/pdf.mjs';
import type { PDFDocumentProxy } from 'pdfjs-dist/types/src/display/api';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/legacy/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

type Props = { file: Blob; initialPage?: number };

export function PdfPaperbook({ file, initialPage = 1 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [document, setDocument] = useState<PDFDocumentProxy>();
  const [pageNumber, setPageNumber] = useState(initialPage);
  const [pageText, setPageText] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    let loaded: PDFDocumentProxy | undefined;
    setError('');
    void file
      .arrayBuffer()
      .then((data) => pdfjs.getDocument({ data }).promise)
      .then((pdf) => {
        loaded = pdf;
        if (active) {
          setDocument(pdf);
          setPageNumber(Math.min(initialPage, pdf.numPages));
        }
      })
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : 'The generated paperbook could not be rendered.'),
      );
    return () => {
      active = false;
      void loaded?.destroy();
    };
  }, [file, initialPage]);

  useEffect(() => {
    if (!document || !canvasRef.current) return;
    let active = true;
    void document
      .getPage(pageNumber)
      .then(async (page) => {
        const viewport = page.getViewport({ scale: 1.15 });
        const canvas = canvasRef.current;
        if (!canvas) return;
        const context = canvas.getContext('2d');
        if (!context) return;
        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);
        await page.render({ canvasContext: context, viewport }).promise;
        const content = await page.getTextContent();
        const text = content.items
          .map((item) => ('str' in item ? item.str : ''))
          .filter(Boolean)
          .join(' ');
        if (active) setPageText(text);
      })
      .catch((cause: unknown) => {
        if (active)
          setError(cause instanceof Error ? cause.message : 'This paperbook page could not be rendered.');
      });
    return () => {
      active = false;
    };
  }, [document, pageNumber]);

  return (
    <div className="paperbook-viewer" aria-label="Generated paperbook viewer">
      <div className="paperbook-toolbar">
        <button
          aria-label="Previous PDF page"
          disabled={!document || pageNumber <= 1}
          onClick={() => setPageNumber((page) => Math.max(1, page - 1))}
        >
          ‹
        </button>
        <label>
          Page{' '}
          <select
            aria-label="PDF page list"
            value={pageNumber}
            disabled={!document}
            onChange={(event) => setPageNumber(Number(event.target.value))}
          >
            {Array.from({ length: document?.numPages ?? 0 }, (_, index) => (
              <option key={index + 1} value={index + 1}>
                {index + 1}
              </option>
            ))}
          </select>{' '}
          of <span data-testid="pdf-page-count">{document?.numPages ?? '…'}</span>
        </label>
        <button
          aria-label="Next PDF page"
          disabled={!document || pageNumber >= document.numPages}
          onClick={() => setPageNumber((page) => Math.min(document?.numPages ?? page, page + 1))}
        >
          ›
        </button>
      </div>
      {error ? (
        <p className="bundle-notice" role="alert">
          {error}
        </p>
      ) : (
        <div className="paperbook-page-frame" aria-label={`Rendered PDF page ${pageNumber}`}>
          <canvas ref={canvasRef} data-testid="pdf-page-canvas" />
        </div>
      )}
      <p
        className="paperbook-page-text"
        data-testid="pdf-page-text"
        aria-label={`Text extracted from PDF page ${pageNumber}`}
      >
        {pageText}
      </p>
      <nav className="paperbook-page-list" aria-label="PDF page list">
        {Array.from({ length: document?.numPages ?? 0 }, (_, index) => (
          <button
            key={index + 1}
            aria-label={`Show PDF page ${index + 1}`}
            aria-current={pageNumber === index + 1 ? 'page' : undefined}
            onClick={() => setPageNumber(index + 1)}
          >
            {index + 1}
          </button>
        ))}
      </nav>
    </div>
  );
}
