"use client";

import { useState, useEffect } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// Configure PDF.js worker — file copied to public/ from pdfjs-dist/build/
if (typeof window !== "undefined" && !pdfjs.GlobalWorkerOptions.workerSrc) {
  pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
}

interface PDFViewerProps {
  file: { data: Uint8Array } | null;
  filename?: string;
  loading?: boolean;
}

export default function PDFViewer({ file, filename, loading = false }: PDFViewerProps) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [scale, setScale] = useState(1);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Reset state when PDF data changes
    setPageNumber(1);
    setScale(1);
    setError(null);
  }, [file]);

  const handleDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
    setError(null);
  };

  const handleDocumentLoadError = (error: Error) => {
    setError(`Error cargando PDF: ${error.message}`);
  };

  const nextPage = () => {
    if (numPages && pageNumber < numPages) {
      setPageNumber(pageNumber + 1);
    }
  };

  const prevPage = () => {
    if (pageNumber > 1) {
      setPageNumber(pageNumber - 1);
    }
  };

  const zoomIn = () => {
    setScale(Math.min(scale + 0.2, 2));
  };

  const zoomOut = () => {
    setScale(Math.max(scale - 0.2, 0.5));
  };

  const fitWidth = () => {
    setScale(1);
  };

  if (loading) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-4 bg-gray-100">
        <div className="spinner" />
        <p className="text-sm text-muted">Cargando PDF…</p>
      </div>
    );
  }

  if (!file) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center bg-gray-100">
        <p className="text-sm text-muted">Selecciona un documento para ver el original</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-red-50 p-4">
        <p className="text-sm font-medium text-red-700">{error}</p>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-col bg-gray-100">
      {/* PDF Toolbar */}
      <div className="flex items-center justify-between border-b border-gray-300 bg-white px-4 py-3">
        <div className="flex items-center gap-2">
          <button
            onClick={prevPage}
            disabled={pageNumber <= 1}
            className="rounded p-2 hover:bg-gray-100 disabled:opacity-50 disabled:hover:bg-transparent"
            title="Página anterior"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
          </button>
          <span className="min-w-24 text-center text-sm font-medium">
            {numPages ? `${pageNumber} / ${numPages}` : ""}
          </span>
          <button
            onClick={nextPage}
            disabled={!numPages || pageNumber >= numPages}
            className="rounded p-2 hover:bg-gray-100 disabled:opacity-50 disabled:hover:bg-transparent"
            title="Siguiente página"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5L15.75 12l-7.5 7.5" />
            </svg>
          </button>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={zoomOut}
            className="rounded p-2 hover:bg-gray-100"
            title="Zoom reducir"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.5 5.5a7.5 7.5 0 0010.5 10.5z" />
            </svg>
          </button>
          <span className="min-w-12 text-center text-sm">{Math.round(scale * 100)}%</span>
          <button
            onClick={zoomIn}
            className="rounded p-2 hover:bg-gray-100"
            title="Zoom aumentar"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </button>
          <button
            onClick={fitWidth}
            className="ml-2 rounded px-3 py-1.5 text-xs font-medium hover:bg-gray-100"
            title="Ajustar ancho"
          >
            Ajustar
          </button>
        </div>
      </div>

      {/* PDF Content */}
      <div className="flex-1 overflow-y-auto bg-gray-200 p-4">
        <div className="flex justify-center">
          <Document
            file={file}
            onLoadSuccess={handleDocumentLoadSuccess}
            onLoadError={handleDocumentLoadError}
            loading={<div className="text-center text-xs text-gray-600">Cargando…</div>}
          >
            <Page pageNumber={pageNumber} scale={scale} renderTextLayer renderAnnotationLayer />
          </Document>
        </div>
      </div>
    </div>
  );
}
