/**
 * Zod validation schemas for document form fields
 * Ensures data integrity before sending to backend
 */

import { z } from 'zod';

// Common validators
const NIFCIFRegex = /^[A-Z]{1,2}[0-9]{7,8}[A-Z0-9]$/i;
const IBANRegex = /^[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}$/;

const nifSchema = z
  .string()
  .regex(NIFCIFRegex, "NIF/CIF inválido")
  .optional()
  .or(z.literal(''));

const ibanSchema = z
  .string()
  .regex(IBANRegex, "IBAN inválido")
  .optional()
  .or(z.literal(''));

const positiveNumber = z
  .number()
  .positive("Debe ser un número positivo")
  .finite("Número inválido")
  .optional()
  .or(z.literal(null));

const currencySchema = z
  .string()
  .regex(/^[A-Z]{3}$/, "Código de moneda inválido (ej: EUR)")
  .optional()
  .or(z.literal(''));

// Invoice Schemas
export const InvoiceReceivedSchema = z.object({
  issuer_name: z.string().min(2, "Nombre del emisor requerido"),
  issuer_nif: nifSchema,
  issuer_address: z.string().optional(),
  issuer_phone: z.string().optional(),
  issuer_iban: ibanSchema,
  client_name: z.string().min(2, "Nombre del cliente requerido"),
  client_nif: nifSchema,
  client_address: z.string().optional(),
  client_phone: z.string().optional(),
  client_iban: ibanSchema,
  invoice_number: z.string().optional(),
  issue_date: z.string().date("Fecha inválida (yyyy-MM-dd)").optional(),
  concept: z.string().max(1000).optional(),
  base_amount: positiveNumber,
  total_amount: z
    .number()
    .positive("Total debe ser positivo")
    .finite("Número inválido"),
  currency: currencySchema,
  payment_method: z.string().optional(),
  billing_period_start: z.string().date().optional(),
  billing_period_end: z.string().date().optional(),
});

export const InvoiceSentSchema = z.object({
  issuer_name: z.string().min(2, "Nombre requerido"),
  issuer_nif: nifSchema,
  issuer_address: z.string().optional(),
  issuer_phone: z.string().optional(),
  issuer_iban: ibanSchema,
  client_name: z.string().min(2, "Nombre del cliente requerido"),
  client_nif: nifSchema,
  client_address: z.string().optional(),
  client_phone: z.string().optional(),
  client_iban: ibanSchema,
  invoice_number: z.string().optional(),
  issue_date: z.string().date().optional(),
  base_amount: positiveNumber,
  total_amount: z.number().positive().finite(),
  currency: currencySchema,
  payment_status: z.string().optional(),
  payment_method: z.string().optional(),
  concept: z.string().max(1000).optional(),
});

export const PaymentReceiptSchema = z.object({
  payment_date: z.string().date().optional(),
  amount: z.number().positive().finite(),
  currency: currencySchema,
  payment_method: z.string().optional(),
  operation_reference: z.string().optional(),
  issuer_name: z.string().optional(),
  card_last_digits: z.string().regex(/^\d{4}$/, "Últimos 4 dígitos").optional(),
  iban: ibanSchema,
});

export const ExpenseTicketSchema = z.object({
  issuer_name: z.string().optional(),
  issue_date: z.string().date().optional(),
  base_amount: positiveNumber,
  total_amount: z.number().positive().finite(),
  currency: currencySchema,
  concept: z.string().max(500).optional(),
  payment_method: z.string().optional(),
});

export const AdministrativeNoticeSchema = z.object({
  issuer_name: z.string().optional(),
  notice_type: z.string().optional(),
  issue_date: z.string().date().optional(),
  deadline: z.string().date().optional(),
  expedient_number: z.string().optional(),
  summary: z.string().max(5000).optional(),
});

export const BankDocumentSchema = z.object({
  bank_name: z.string().min(1, "Nombre del banco requerido"),
  document_date: z.string().date().optional(),
  iban: ibanSchema,
});

export const ContractSchema = z.object({
  contract_date: z.string().date().optional(),
  subject: z.string().optional(),
  duration: z.string().optional(),
  economic_terms: z.string().max(5000).optional(),
  signed: z.boolean().optional(),
});

// Get schema for document type
export function getValidationSchema(documentType: string) {
  const schemas: Record<string, z.ZodType<any>> = {
    invoice_received: InvoiceReceivedSchema,
    invoice_sent: InvoiceSentSchema,
    payment_receipt: PaymentReceiptSchema,
    expense_ticket: ExpenseTicketSchema,
    administrative_notice: AdministrativeNoticeSchema,
    bank_document: BankDocumentSchema,
    contract: ContractSchema,
    other: z.record(z.string(), z.any()),
  };
  return schemas[documentType] || z.record(z.string(), z.any());
}

/**
 * Validate a single field against the schema
 */
export function validateField(
  documentType: string,
  fieldKey: string,
  value: unknown
): { valid: boolean; error?: string } {
  try {
    const schema = getValidationSchema(documentType) as z.ZodObject<any>;
    
    // Get the field schema from the object
    const fieldSchema = schema.shape[fieldKey];
    if (!fieldSchema) {
      // Field not found in schema, allow it
      return { valid: true };
    }
    
    // Validate just this field
    fieldSchema.parse(value);
    return { valid: true };
  } catch (error) {
    if (error instanceof z.ZodError) {
      const message = (error as any).errors?.[0]?.message || "Valor inválido";
      return { valid: false, error: message };
    }
    return { valid: false, error: "Validación fallida" };
  }
}

/**
 * Validate entire document
 */
export function validateDocument(
  documentType: string,
  data: Record<string, unknown>
): { valid: boolean; errors: Record<string, string> } {
  try {
    const schema = getValidationSchema(documentType);
    schema.parse(data);
    return { valid: true, errors: {} };
  } catch (error) {
    const errors: Record<string, string> = {};
    if (error instanceof z.ZodError) {
      const zodError = error as any;
      if (zodError.errors && Array.isArray(zodError.errors)) {
        zodError.errors.forEach((err: any) => {
          const path = err.path?.join('.') || 'unknown';
          errors[path] = err.message;
        });
      }
    }
    return { valid: false, errors };
  }
}
