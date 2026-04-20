import Papa from "papaparse";

// @ts-ignore - read-excel-file subpath types
import readExcelFile from "read-excel-file/browser";

export interface ParsedData {
  headers: string[];
  rows: string[][];
}

export async function parseFile(file: File): Promise<ParsedData> {
  const maxSize = 5 * 1024 * 1024; // 5MB
  const maxRows = 500;

  if (file.size > maxSize) {
    throw new Error(`El archivo es demasiado grande. Máximo 5MB. Recibido: ${(file.size / 1024 / 1024).toFixed(2)}MB`);
  }

  const extension = file.name.toLowerCase().split(".").pop();

  if (extension === "csv") {
    return parseCSV(file, maxRows);
  } else if (extension === "xlsx" || extension === "xls") {
    return parseExcel(file, maxRows);
  } else {
    throw new Error(`Formato no soportado: ${extension}. Usa CSV o XLSX.`);
  }
}

async function parseCSV(file: File, maxRows: number): Promise<ParsedData> {
  return new Promise((resolve, reject) => {
    Papa.parse(file, {
      header: false,
      skipEmptyLines: true,
      dynamicTyping: false,
      transformHeader: (h: string) => h.trim(),
      complete: (results: any) => {
        if (results.errors.length > 0) {
          reject(new Error(`Error al parsear CSV: ${results.errors[0].message}`));
          return;
        }

        const rows = results.data as string[][];
        if (rows.length < 2) {
          reject(new Error("El archivo debe tener al menos headers y una fila de datos"));
          return;
        }

        const headers = rows[0].map((h: string) => h.trim()).filter((h: string) => h.length > 0);
        const dataRows = rows
          .slice(1, maxRows + 1)
          .map((row: string[]) => row.slice(0, headers.length).map((cell: string) => String(cell || "").trim()))
          .filter((row: string[]) => row.some((cell: string) => cell.length > 0)); // Elimina filas completamente vacías

        if (dataRows.length === 0) {
          reject(new Error("No se encontraron filas de datos en el archivo"));
          return;
        }

        if (rows.length > maxRows + 1) {
          console.warn(`Archivo tiene ${rows.length - 1} filas. Solo se procesarán las primeras ${maxRows}.`);
        }

        resolve({
          headers,
          rows: dataRows,
        });
      },
      error: (error: any) => {
        reject(new Error(`Error al parsear CSV: ${error.message}`));
      },
    });
  });
}

async function parseExcel(file: File, maxRows: number): Promise<ParsedData> {
  try {
    const rows = (await readExcelFile(file)) as any[];

    if (rows.length < 2) {
      throw new Error("El archivo debe tener al menos headers y una fila de datos");
    }

    const headers = rows[0]
      .map((h: any) => String(h || "").trim())
      .filter((h: string) => h.length > 0);

    const dataRows = rows
      .slice(1, maxRows + 1)
      .map((row: any[]) =>
        row
          .slice(0, headers.length)
          .map((cell: any) => String(cell || "").trim())
      )
      .filter((row: string[]) => row.some((cell: string) => cell.length > 0)); // Elimina filas completamente vacías

    if (dataRows.length === 0) {
      throw new Error("No se encontraron filas de datos en el archivo");
    }

    if (rows.length > maxRows + 1) {
      console.warn(`Archivo tiene ${rows.length - 1} filas. Solo se procesarán las primeras ${maxRows}.`);
    }

    return {
      headers,
      rows: dataRows,
    };
  } catch (error) {
    throw new Error(`Error al parsear Excel: ${error instanceof Error ? error.message : "Error desconocido"}`);
  }
}
