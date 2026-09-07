export type WidgetStatus = "DRAFT" | "ACTIVE" | "INACTIVE";

export type WidgetAppearance = {
  primary_color?: string;
  text_color?: string;
  launcher_position?: string;
  launcher_text?: string;
  border_radius_px?: number;
  z_index?: number;
  logo_url?: string | null;
};

export type ChatWidget = {
  id: string;
  organization_id: string;
  public_id: string;
  name: string;
  status: WidgetStatus;
  allowed_domains: string[];
  appearance: WidgetAppearance;
  welcome_message: string;
  offline_message: string | null;
  require_email: boolean;
  require_name: boolean;
  created_at: string;
  updated_at: string;
};

export type PublicWidgetConfig = {
  public_id: string;
  name: string;
  status: WidgetStatus;
  welcome_message: string;
  offline_message: string | null;
  require_name: boolean;
  require_email: boolean;
  appearance: WidgetAppearance;
};

export type WidgetSession = {
  visitor_key: string;
  customer_id: string;
  visitor_token: string;
  expires_at: string;
  conversation_id: string | null;
};

export type EmbedSnippet = {
  public_id: string;
  snippet: string;
  widget_js_url: string;
  frame_url: string;
};

export type WidgetCreateInput = {
  name: string;
  status?: WidgetStatus;
  allowed_domains?: string[];
  appearance?: WidgetAppearance;
  welcome_message?: string;
  offline_message?: string | null;
  require_email?: boolean;
  require_name?: boolean;
};

export type WidgetUpdateInput = Partial<WidgetCreateInput>;

export function storageKey(publicId: string) {
  return `sp_widget_${publicId}`;
}

export type StoredVisitorState = {
  visitor_key: string;
  visitor_token: string;
  customer_id: string;
  conversation_id?: string | null;
};
