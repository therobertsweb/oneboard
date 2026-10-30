import 'dart:convert';

enum FieldType {
  text,
  password,
  multiline,
  integer,
  boolean,
  date,
  month,
  dropdown,
  stringList,
  folder,
  file,
}

class FieldSpec {
  const FieldSpec(
    this.name,
    this.type, {
    this.options = const <String>[],
    this.min,
    this.max,
    this.hint = '',
    this.optional = false,
  });

  final String name;
  final FieldType type;
  final List<String> options;
  final num? min;
  final num? max;
  final String hint;
  final bool optional;
}

class FeatureAction {
  const FeatureAction(
    this.label,
    this.method,
    this.path, {
    this.body = '',
    this.help = '',
    this.uploadField,
    this.fields = const <FieldSpec>[],
    this.coveredByPanel = false,
  });

  final String label;
  final String method;
  final String path;
  final String body;
  final String help;
  final String? uploadField;
  final List<FieldSpec> fields;

  /// True when a visual panel already performs this action, so the generic
  /// action button is hidden and every key or flow is entered exactly once.
  final bool coveredByPanel;

  FieldSpec? specFor(String name) {
    for (final spec in fields) {
      if (spec.name == name) return spec;
    }
    return null;
  }
}

class FeaturePage {
  const FeaturePage(this.title, this.description, this.endpoint, this.actions);

  final String title;
  final String description;
  final String endpoint;
  final List<FeatureAction> actions;
}

/// Converts dialog text into the JSON value the backend expects.
/// Throws [FormatException] with an English message when the text is invalid.
Object? coerceFieldValue(FieldSpec? spec, Object? initial, String rawText) {
  final text = rawText.trim();
  if (spec != null) {
    if (spec.optional && text.isEmpty) return '';
    switch (spec.type) {
      case FieldType.boolean:
        return text.toLowerCase() == 'true';
      case FieldType.integer:
        final parsed = int.tryParse(text);
        if (parsed == null) {
          throw FormatException('“${spec.name}” must be a whole number.');
        }
        var value = parsed;
        if (spec.min != null && value < spec.min!) value = spec.min!.toInt();
        if (spec.max != null && value > spec.max!) value = spec.max!.toInt();
        return value;
      case FieldType.dropdown:
        if (!spec.options.contains(text)) {
          throw FormatException('Choose a valid value for “${spec.name}”.');
        }
        return text;
      case FieldType.date:
        final match = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$').firstMatch(text);
        var validDate = false;
        if (match != null) {
          final year = int.parse(match.group(1)!);
          final month = int.parse(match.group(2)!);
          final day = int.parse(match.group(3)!);
          final parsed = DateTime(year, month, day);
          validDate =
              parsed.year == year && parsed.month == month && parsed.day == day;
        }
        if (!validDate) {
          throw FormatException(
            '“${spec.name}” must be a date like 2026-11-01.',
          );
        }
        return text;
      case FieldType.month:
        if (!RegExp(r'^\d{4}-(0[1-9]|1[0-2])$').hasMatch(text)) {
          throw FormatException('“${spec.name}” must be a month like 2026-10.');
        }
        return text;
      case FieldType.stringList:
        if (text.isEmpty) return <String>[];
        if (text.startsWith('[')) {
          final decoded = jsonDecode(text);
          if (decoded is! List) {
            throw FormatException('“${spec.name}” must be a list.');
          }
          return decoded
              .map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList();
        }
        return text
            .split(',')
            .map((part) => part.trim())
            .where((part) => part.isNotEmpty)
            .toList();
      case FieldType.text:
      case FieldType.password:
      case FieldType.multiline:
      case FieldType.folder:
      case FieldType.file:
        return text;
    }
  }
  if (initial is Map || initial is List) {
    if (text.isEmpty) return initial;
    return jsonDecode(text);
  }
  if (initial is bool) return text.toLowerCase() == 'true';
  if (initial is num && num.tryParse(text) != null) return num.parse(text);
  return text;
}

const featurePages = <FeaturePage>[
  FeaturePage(
    'Studio',
    'Files, AI assistance, updates, and site publishing.',
    '/api/site-manager',
    [
      FeatureAction(
        'Connect folder or project',
        'POST',
        '/api/site-manager/connect',
        body: '{\n  "path": ""\n}',
        help: 'Choose a local folder or shared project.',
      ),
      FeatureAction(
        'Run site assistant',
        'POST',
        '/api/site-manager/codex-update',
        body: '{\n  "prompt": "Describe the change you need"\n}',
        help:
            'Describe the change you need. The assistant can create and edit files in the connected local project.',
        fields: [FieldSpec('prompt', FieldType.multiline)],
      ),
      FeatureAction(
        'Generate SEO content',
        'POST',
        '/api/site-manager/seo-content',
        body:
            '{\n  "title": "Page title",\n  "keyword": "target keyword",\n  "tone": "professional",\n  "audience": "customers",\n  "cta": "Contact us"\n}',
        fields: [
          FieldSpec('title', FieldType.text),
          FieldSpec('keyword', FieldType.text),
          FieldSpec('tone', FieldType.text),
          FieldSpec('audience', FieldType.text),
          FieldSpec('cta', FieldType.text),
        ],
      ),
      FeatureAction(
        'Upload site image',
        'POST',
        '/api/site-manager/assets/upload',
        uploadField: 'asset',
      ),
      FeatureAction(
        'Create backup',
        'POST',
        '/api/site-manager/backup',
        body: '{}',
      ),
      FeatureAction(
        'Restore backup',
        'POST',
        '/api/site-manager/restore',
        body: '{\n  "backup_id": 1\n}',
        fields: [FieldSpec('backup_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Create SSH key',
        'POST',
        '/api/site-manager/ssh-key',
        body: '{}',
      ),
      FeatureAction(
        'Save remote connection',
        'POST',
        '/api/site-manager/remote',
        body:
            '{\n  "host": "example.com",\n  "port": 22,\n  "username": "deploy",\n  "remote_path": "/var/www/site",\n  "auth_method": "key",\n  "key_path": "",\n  "password": ""\n}',
        fields: [
          FieldSpec('host', FieldType.text),
          FieldSpec('port', FieldType.integer, min: 1, max: 65535),
          FieldSpec('username', FieldType.text),
          FieldSpec('remote_path', FieldType.text),
          FieldSpec(
            'auth_method',
            FieldType.dropdown,
            options: ['key', 'password'],
          ),
          FieldSpec('key_path', FieldType.file),
          FieldSpec('password', FieldType.password),
        ],
      ),
      FeatureAction(
        'Test remote connection',
        'POST',
        '/api/site-manager/remote/test',
        body:
            '{\n  "host": "example.com",\n  "port": 22,\n  "username": "deploy",\n  "remote_path": "/var/www/site",\n  "auth_method": "key",\n  "password": ""\n}',
        fields: [
          FieldSpec('host', FieldType.text),
          FieldSpec('port', FieldType.integer, min: 1, max: 65535),
          FieldSpec('username', FieldType.text),
          FieldSpec('remote_path', FieldType.text),
          FieldSpec(
            'auth_method',
            FieldType.dropdown,
            options: ['key', 'password'],
          ),
          FieldSpec('password', FieldType.password),
        ],
      ),
      FeatureAction(
        'Sync remote site',
        'POST',
        '/api/site-manager/remote/sync',
        body: '{}',
      ),
      FeatureAction(
        'Run terminal command',
        'POST',
        '/api/site-manager/terminal/run',
        body: '{\n  "command": "npm run build"\n}',
        fields: [FieldSpec('command', FieldType.text)],
      ),
      FeatureAction(
        'Delete file',
        'POST',
        '/api/site-manager/files/delete',
        body: '{\n  "path": "index.html"\n}',
        fields: [FieldSpec('path', FieldType.text)],
      ),
      FeatureAction(
        'Approve update',
        'POST',
        '/api/site-manager/update/action',
        body: '{\n  "update_id": 1,\n  "action": "approve"\n}',
        fields: [
          FieldSpec('update_id', FieldType.integer, min: 1),
          FieldSpec(
            'action',
            FieldType.dropdown,
            options: ['approve', 'publish', 'restore'],
          ),
        ],
      ),
      FeatureAction(
        'Publish update remotely',
        'POST',
        '/api/site-manager/update/action',
        body: '{\n  "update_id": 1,\n  "action": "publish"\n}',
        fields: [
          FieldSpec('update_id', FieldType.integer, min: 1),
          FieldSpec(
            'action',
            FieldType.dropdown,
            options: ['approve', 'publish', 'restore'],
          ),
        ],
      ),
      FeatureAction(
        'Restore update',
        'POST',
        '/api/site-manager/update/action',
        body: '{\n  "update_id": 1,\n  "action": "restore"\n}',
        fields: [
          FieldSpec('update_id', FieldType.integer, min: 1),
          FieldSpec(
            'action',
            FieldType.dropdown,
            options: ['approve', 'publish', 'restore'],
          ),
        ],
      ),
      FeatureAction(
        'Remove project',
        'POST',
        '/api/site-manager/projects/remove',
        body: '{\n  "project_id": 1\n}',
        fields: [FieldSpec('project_id', FieldType.integer, min: 1)],
      ),
    ],
  ),
  FeaturePage(
    'Preview',
    'Preview pages and prepare targeted updates.',
    '/api/site-manager/intelligence',
    [
      FeatureAction(
        'Save selected element',
        'POST',
        '/api/site-manager/preview/select',
        body:
            '{\n  "page": "/",\n  "selector": "h1",\n  "tag": "h1",\n  "text": "Selected text"\n}',
        fields: [
          FieldSpec('page', FieldType.text),
          FieldSpec('selector', FieldType.text),
          FieldSpec('tag', FieldType.text),
          FieldSpec('text', FieldType.text),
        ],
      ),
      FeatureAction(
        'Clear selection',
        'DELETE',
        '/api/site-manager/preview/select',
      ),
      FeatureAction(
        'Compare update',
        'GET',
        '/api/site-manager/updates/:update_id/compare',
        help: 'Choose the update you want to compare.',
        fields: [FieldSpec('update_id', FieldType.integer, min: 1)],
      ),
    ],
  ),
  FeaturePage(
    'Site & Brand',
    'Site identity, client details, and brand preferences.',
    '/api/site-manager/site',
    [
      FeatureAction(
        'Save site and brand details',
        'POST',
        '/api/site-manager/site',
        body:
            '{\n  "display_name": "My site",\n  "client_name": "Client",\n  "brand": {\n    "business_name": "Company",\n    "tagline": "Tagline",\n    "services": "Services",\n    "audience": "Audience",\n    "tone": "Approachable",\n    "website": "https://example.com",\n    "phone": "",\n    "email": "",\n    "address": "",\n    "colors": {"primary":"", "secondary":"", "accent":""},\n    "fonts": {"headings":"", "body":""},\n    "notes": ""\n  }\n}',
        fields: [
          FieldSpec('display_name', FieldType.text),
          FieldSpec('client_name', FieldType.text),
        ],
      ),
      FeatureAction(
        'Upload brand logo',
        'POST',
        '/api/site-manager/site/logo',
        uploadField: 'logo',
      ),
      FeatureAction('View image library', 'GET', '/api/ai/images?scope=site'),
      FeatureAction(
        'Connect Search Console',
        'GET',
        '/api/google-search-console/connect',
        coveredByPanel: true,
        help:
            'ONEBoard will open your browser to complete Google authorization.',
      ),
      FeatureAction(
        'Select Google property',
        'POST',
        '/api/google-search-console/site',
        coveredByPanel: true,
        body: '{\n  "site_url": "https://example.com/"\n}',
        fields: [FieldSpec('site_url', FieldType.text)],
      ),
      FeatureAction(
        'Disconnect Search Console',
        'POST',
        '/api/google-search-console/disconnect',
        coveredByPanel: true,
      ),
    ],
  ),
  FeaturePage(
    'Site Health',
    'Detected issues, explanations, and fixes.',
    '/api/site-manager/health',
    [
      FeatureAction(
        'Scan site',
        'POST',
        '/api/site-manager/health/scan',
        body: '{\n  "skip_external": false\n}',
        fields: [FieldSpec('skip_external', FieldType.boolean)],
      ),
      FeatureAction(
        'Explain issues with AI',
        'POST',
        '/api/site-manager/health/summary',
        body: '{}',
      ),
      FeatureAction(
        'Apply automatic fixes',
        'POST',
        '/api/site-manager/health/fix-all',
        body: '{}',
      ),
      FeatureAction(
        'Fix issues with AI',
        'POST',
        '/api/site-manager/health/ai-fix',
        body: '{}',
      ),
      FeatureAction(
        'Apply fix',
        'POST',
        '/api/site-manager/health/findings/:finding_id/apply',
        fields: [FieldSpec('finding_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Ignore finding',
        'POST',
        '/api/site-manager/health/findings/:finding_id/ignore',
        fields: [FieldSpec('finding_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Reopen finding',
        'POST',
        '/api/site-manager/health/findings/:finding_id/reopen',
        fields: [FieldSpec('finding_id', FieldType.integer, min: 1)],
      ),
    ],
  ),
  FeaturePage(
    'Requests',
    'Client requests and approvals.',
    '/api/site-manager/requests',
    [
      FeatureAction(
        'Create client link',
        'POST',
        '/api/site-manager/request-links',
        body: '{\n  "label": "Site review",\n  "expires_days": 30\n}',
        fields: [
          FieldSpec('label', FieldType.text),
          FieldSpec('expires_days', FieldType.integer, min: 1),
        ],
      ),
      FeatureAction(
        'Revoke link',
        'DELETE',
        '/api/site-manager/request-links/:link_id',
        fields: [FieldSpec('link_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Open conversation',
        'GET',
        '/api/site-manager/requests/:request_id',
        fields: [FieldSpec('request_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Comment on request',
        'POST',
        '/api/site-manager/requests/:request_id/comments',
        body: '{\n  "body": "Team comment"\n}',
        fields: [
          FieldSpec('request_id', FieldType.integer, min: 1),
          FieldSpec('body', FieldType.multiline),
        ],
      ),
      FeatureAction(
        'Update status',
        'POST',
        '/api/site-manager/requests/:request_id/status',
        body: '{\n  "status": "in_review"\n}',
        fields: [
          FieldSpec('request_id', FieldType.integer, min: 1),
          FieldSpec(
            'status',
            FieldType.dropdown,
            options: ['open', 'in_review', 'proposed', 'done'],
          ),
        ],
      ),
      FeatureAction(
        'Delete request',
        'DELETE',
        '/api/site-manager/requests/:request_id',
        fields: [FieldSpec('request_id', FieldType.integer, min: 1)],
      ),
    ],
  ),
  FeaturePage(
    'Calendar',
    'Plan and run scheduled updates.',
    '/api/site-manager/calendar',
    [
      FeatureAction(
        'Create event',
        'POST',
        '/api/site-manager/calendar',
        body:
            '{\n  "kind": "promo",\n  "title": "New promotion",\n  "brief": "Update details",\n  "page": "",\n  "starts_on": "",\n  "ends_on": ""\n}',
        fields: [
          FieldSpec(
            'kind',
            FieldType.dropdown,
            options: ['promo', 'blog', 'prices', 'note'],
          ),
          FieldSpec('title', FieldType.text),
          FieldSpec('brief', FieldType.multiline),
          FieldSpec('page', FieldType.text),
          FieldSpec('starts_on', FieldType.date),
          FieldSpec('ends_on', FieldType.date, optional: true),
        ],
      ),
      FeatureAction(
        'Update event',
        'POST',
        '/api/site-manager/calendar/:event_id',
        body:
            '{"kind":"note","title":"","brief":"","page":"","starts_on":"","ends_on":""}',
        fields: [
          FieldSpec('event_id', FieldType.integer, min: 1),
          FieldSpec(
            'kind',
            FieldType.dropdown,
            options: ['promo', 'blog', 'prices', 'note'],
          ),
          FieldSpec('title', FieldType.text),
          FieldSpec('brief', FieldType.multiline),
          FieldSpec('page', FieldType.text),
          FieldSpec('starts_on', FieldType.date),
          FieldSpec('ends_on', FieldType.date, optional: true),
        ],
      ),
      FeatureAction(
        'Run event',
        'POST',
        '/api/site-manager/calendar/:event_id/execute',
        fields: [FieldSpec('event_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Cancel event',
        'POST',
        '/api/site-manager/calendar/:event_id/cancel',
        fields: [FieldSpec('event_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Delete event',
        'DELETE',
        '/api/site-manager/calendar/:event_id',
        fields: [FieldSpec('event_id', FieldType.integer, min: 1)],
      ),
    ],
  ),
  FeaturePage(
    'Contact Inbox',
    'Messages received through your site’s contact forms.',
    '/api/site-manager/inbox',
    [
      FeatureAction(
        'View embed form',
        'GET',
        '/api/site-manager/inbox/snippet',
      ),
      FeatureAction(
        'Create form token',
        'POST',
        '/api/site-manager/inbox/token',
        body: '{\n  "label": "Contact form"\n}',
        fields: [FieldSpec('label', FieldType.text)],
      ),
      FeatureAction(
        'Revoke token',
        'DELETE',
        '/api/site-manager/inbox/token/:token_id',
        fields: [FieldSpec('token_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Mark message as handled',
        'POST',
        '/api/site-manager/inbox/:message_id/attend',
        fields: [FieldSpec('message_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Reopen message',
        'POST',
        '/api/site-manager/inbox/:message_id/reopen',
        fields: [FieldSpec('message_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Delete message',
        'DELETE',
        '/api/site-manager/inbox/:message_id',
        fields: [FieldSpec('message_id', FieldType.integer, min: 1)],
      ),
    ],
  ),
  FeaturePage(
    'Alerts',
    'Keep an eye on availability, certificates, and publishing.',
    '/api/site-manager/alerts',
    [
      FeatureAction(
        'Create monitor',
        'POST',
        '/api/site-manager/alerts/rules',
        body:
            '{\n  "kind": "uptime",\n  "target": "https://example.com",\n  "name": "Primary site",\n  "threshold_days": 14\n}',
        fields: [
          FieldSpec('kind', FieldType.dropdown, options: ['uptime', 'tls']),
          FieldSpec('target', FieldType.text),
          FieldSpec('name', FieldType.text),
          FieldSpec('threshold_days', FieldType.integer, min: 1, max: 365),
        ],
      ),
      FeatureAction(
        'Update monitor',
        'POST',
        '/api/site-manager/alerts/rules/:rule_id',
        body: '{"name":"","enabled":true,"threshold_days":14}',
        fields: [
          FieldSpec('rule_id', FieldType.integer, min: 1),
          FieldSpec('enabled', FieldType.boolean),
          FieldSpec('name', FieldType.text),
          FieldSpec('threshold_days', FieldType.integer, min: 1, max: 365),
        ],
      ),
      FeatureAction(
        'Delete monitor',
        'DELETE',
        '/api/site-manager/alerts/rules/:rule_id',
        fields: [FieldSpec('rule_id', FieldType.integer, min: 1)],
      ),
      FeatureAction('Check now', 'POST', '/api/site-manager/alerts/check'),
      FeatureAction(
        'Acknowledge alert',
        'POST',
        '/api/site-manager/alerts/:alert_id/ack',
        fields: [FieldSpec('alert_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Resolve alert',
        'POST',
        '/api/site-manager/alerts/:alert_id/resolve',
        fields: [FieldSpec('alert_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Reopen alert',
        'POST',
        '/api/site-manager/alerts/:alert_id/reopen',
        fields: [FieldSpec('alert_id', FieldType.integer, min: 1)],
      ),
    ],
  ),
  FeaturePage(
    'Reports',
    'Monthly summaries and reports to share with clients.',
    '/api/site-manager/reports',
    [
      FeatureAction(
        'Create shareable report',
        'POST',
        '/api/site-manager/reports',
        body: '{\n  "period": "2026-10",\n  "title": "Monthly report"\n}',
        fields: [
          FieldSpec('period', FieldType.month),
          FieldSpec('title', FieldType.text),
        ],
      ),
      FeatureAction(
        'View report',
        'GET',
        '/api/site-manager/reports/:report_id',
        fields: [FieldSpec('report_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Revoke report',
        'DELETE',
        '/api/site-manager/reports/:report_id',
        fields: [FieldSpec('report_id', FieldType.integer, min: 1)],
      ),
    ],
  ),
  FeaturePage(
    'Social',
    'Create Buffer content. Selected images are shared through your media server HTTPS URL.',
    '/api/social/buffer/posts',
    [
      FeatureAction(
        'View connected channels',
        'GET',
        '/api/social/buffer/channels',
        coveredByPanel: true,
      ),
      FeatureAction(
        'View post ideas',
        'GET',
        '/api/social/suggestions',
        coveredByPanel: true,
      ),
      FeatureAction(
        'Generate ideas with AI',
        'POST',
        '/api/social/ideas',
        body: '{\n  "hint": "Seasonal promotion"\n}',
        fields: [FieldSpec('hint', FieldType.text)],
        coveredByPanel: true,
      ),
      FeatureAction(
        'Write post',
        'POST',
        '/api/social/generate',
        body: '{\n  "prompt": "Announce a new collection"\n}',
        fields: [FieldSpec('prompt', FieldType.multiline)],
        coveredByPanel: true,
      ),
      FeatureAction(
        'View history',
        'GET',
        '/api/social/buffer/posts',
        coveredByPanel: true,
      ),
      FeatureAction(
        'Create draft or publish',
        'POST',
        '/api/social/buffer/posts',
        coveredByPanel: true,
        body:
            '{\n  "channel_ids": [],\n  "text": "Post text",\n  "post_type": "post",\n  "draft": true,\n  "publish_now": false\n}',
        fields: [
          FieldSpec(
            'channel_ids',
            FieldType.stringList,
            hint: 'Comma-separated channel IDs from “View connected channels”.',
          ),
          FieldSpec('text', FieldType.multiline),
          FieldSpec(
            'post_type',
            FieldType.dropdown,
            options: ['post', 'story', 'reel'],
          ),
          FieldSpec('draft', FieldType.boolean),
          FieldSpec('publish_now', FieldType.boolean),
        ],
      ),
      FeatureAction(
        'Edit image with AI',
        'POST',
        '/api/social/images/edit',
        coveredByPanel: true,
        body:
            '{\n  "image_url": "https://example.com/image.jpg",\n  "instruction": "Add a summer background"\n}',
        fields: [
          FieldSpec('image_url', FieldType.text),
          FieldSpec('instruction', FieldType.text),
        ],
      ),
      FeatureAction(
        'Upload social image',
        'POST',
        '/api/social/images/upload',
        coveredByPanel: true,
        uploadField: 'image',
        help:
            'The app saves a private copy and publishes it to your media server so Buffer can download the image.',
      ),
    ],
  ),
  FeaturePage(
    'Teams',
    'Members, permissions, projects, and invitations.',
    '/api/teams',
    [
      FeatureAction(
        'Create team',
        'POST',
        '/api/teams',
        body: '{\n  "name": "My team",\n  "description": "Description"\n}',
        fields: [
          FieldSpec('name', FieldType.text),
          FieldSpec('description', FieldType.text),
        ],
      ),
      FeatureAction(
        'View team',
        'GET',
        '/api/teams/:team_id',
        fields: [FieldSpec('team_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Edit team',
        'POST',
        '/api/teams/:team_id',
        body: '{\n  "name": "Updated name"\n}',
        fields: [
          FieldSpec('team_id', FieldType.integer, min: 1),
          FieldSpec('name', FieldType.text),
        ],
      ),
      FeatureAction(
        'Invite member',
        'POST',
        '/api/teams/:team_id/invites',
        body: '{\n  "email": "person@example.com",\n  "role": "editor"\n}',
        fields: [
          FieldSpec('team_id', FieldType.integer, min: 1),
          FieldSpec('email', FieldType.text),
          FieldSpec(
            'role',
            FieldType.dropdown,
            options: ['admin', 'editor', 'viewer', 'client'],
          ),
        ],
      ),
      FeatureAction(
        'Revoke invitation',
        'DELETE',
        '/api/teams/:team_id/invites/:invite_id',
        fields: [
          FieldSpec('team_id', FieldType.integer, min: 1),
          FieldSpec('invite_id', FieldType.integer, min: 1),
        ],
      ),
      FeatureAction(
        'Update member',
        'POST',
        '/api/teams/:team_id/members/:user_id',
        body: '{\n  "role": "editor"\n}',
        fields: [
          FieldSpec('team_id', FieldType.integer, min: 1),
          FieldSpec('user_id', FieldType.integer, min: 1),
          FieldSpec(
            'role',
            FieldType.dropdown,
            options: ['admin', 'editor', 'viewer', 'client'],
          ),
        ],
      ),
      FeatureAction(
        'Remove member',
        'DELETE',
        '/api/teams/:team_id/members/:user_id',
        fields: [
          FieldSpec('team_id', FieldType.integer, min: 1),
          FieldSpec('user_id', FieldType.integer, min: 1),
        ],
      ),
      FeatureAction(
        'Share folder',
        'POST',
        '/api/teams/:team_id/projects',
        body: '{\n  "path": ""\n}',
        help: 'Choose a local folder on this Mac to share with the team.',
        fields: [
          FieldSpec('team_id', FieldType.integer, min: 1),
          FieldSpec('path', FieldType.folder),
        ],
      ),
      FeatureAction(
        'Unlink folder',
        'DELETE',
        '/api/teams/:team_id/projects/:project_id',
        fields: [
          FieldSpec('team_id', FieldType.integer, min: 1),
          FieldSpec('project_id', FieldType.integer, min: 1),
        ],
      ),
      FeatureAction(
        'Accept invitation',
        'POST',
        '/api/teams/invites/accept',
        body: '{\n  "token": "invitation-token"\n}',
        fields: [FieldSpec('token', FieldType.text)],
      ),
      FeatureAction(
        'Accept invitation by ID',
        'POST',
        '/api/teams/invites/:invite_id/accept',
        fields: [FieldSpec('invite_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Transfer ownership',
        'POST',
        '/api/teams/:team_id/transfer',
        body: '{\n  "user_id": 2\n}',
        fields: [
          FieldSpec('team_id', FieldType.integer, min: 1),
          FieldSpec('user_id', FieldType.integer, min: 1),
        ],
      ),
      FeatureAction(
        'Leave team',
        'POST',
        '/api/teams/:team_id/leave',
        fields: [FieldSpec('team_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Delete team',
        'DELETE',
        '/api/teams/:team_id',
        fields: [FieldSpec('team_id', FieldType.integer, min: 1)],
      ),
    ],
  ),
  FeaturePage(
    'Security',
    'Check the public security status of a domain.',
    '/api/security-scan',
    [
      FeatureAction(
        'Prepare repair',
        'GET',
        '/api/security-scan/:scan_id/repair',
        fields: [FieldSpec('scan_id', FieldType.integer, min: 1)],
      ),
      FeatureAction(
        'Scan domain',
        'POST',
        '/api/security-scan',
        body: '{\n  "domain": "example.com"\n}',
        fields: [FieldSpec('domain', FieldType.text)],
      ),
    ],
  ),
  FeaturePage(
    'Notifications',
    'Activity from requests, contacts, and alerts.',
    '/api/notifications',
    [
      FeatureAction(
        'Mark notification as read',
        'POST',
        '/api/notifications/:notification_id/read',
        fields: [FieldSpec('notification_id', FieldType.integer, min: 1)],
      ),
      FeatureAction('Mark all as read', 'POST', '/api/notifications/read-all'),
    ],
  ),
  FeaturePage(
    'Settings',
    'Account, Muse credentials, and preferences.',
    '/api/settings',
    [
      FeatureAction(
        'Save account and company',
        'POST',
        '/api/settings/account',
        body: '{\n  "name": "Name",\n  "company_name": "Company"\n}',
        fields: [
          FieldSpec('name', FieldType.text),
          FieldSpec('company_name', FieldType.text),
        ],
        coveredByPanel: true,
      ),
      FeatureAction(
        'Connect Buffer',
        'POST',
        '/api/settings/account',
        body: '{"buffer_api_key":"", "current_password":""}',
        help: 'Enter your Buffer API key to load channels and publish posts.',
        fields: [
          FieldSpec('buffer_api_key', FieldType.password),
          FieldSpec('current_password', FieldType.password),
        ],
        coveredByPanel: true,
      ),
      FeatureAction(
        'Save Muse credentials',
        'POST',
        '/api/settings/ai-credentials',
        body: '{\n  "current_password": "",\n  "muse_api_key": ""\n}',
        help: 'Muse is the only AI provider in this app.',
        fields: [
          FieldSpec('current_password', FieldType.password),
          FieldSpec('muse_api_key', FieldType.password),
        ],
        coveredByPanel: true,
      ),
      FeatureAction(
        'Save Muse model',
        'POST',
        '/api/settings/ai-policy',
        body: '{\n  "model": ""\n}',
        help: 'Muse is the only AI provider. Leave the model empty for the default.',
        fields: [FieldSpec('model', FieldType.text)],
        coveredByPanel: true,
      ),
      FeatureAction('View Muse models', 'GET', '/api/settings/muse-models'),
      FeatureAction(
        'Refresh Muse models',
        'POST',
        '/api/settings/muse-models/refresh',
      ),
      FeatureAction(
        'Google diagnostics',
        'GET',
        '/api/settings/google/diagnostics',
        coveredByPanel: true,
      ),
      FeatureAction(
        'Run an AI task',
        'POST',
        '/api/ai/run',
        body:
            '{\n  "task_type": "assistant",\n  "prompt": "Write a short description for the site"\n}',
        fields: [
          FieldSpec('task_type', FieldType.text),
          FieldSpec('prompt', FieldType.multiline),
        ],
      ),
      FeatureAction('View AI runs', 'GET', '/api/ai/runs'),
      FeatureAction(
        'Generate image',
        'POST',
        '/api/ai/images',
        body:
            '{\n  "prompt": "Illustration for the site homepage",\n  "output_format": "png"\n}',
        fields: [
          FieldSpec('prompt', FieldType.multiline),
          FieldSpec('output_format', FieldType.text),
        ],
      ),
    ],
  ),
];

/// Populate only editable fields; never copy IDs, credentials or server metadata.
Map<String, dynamic> actionInitialValues(
  FeatureAction action, {
  Map<String, dynamic>? record,
  DateTime? now,
}) {
  final values = action.body.isEmpty
      ? <String, dynamic>{}
      : (jsonDecode(action.body) as Map).cast<String, dynamic>();
  final today = (now ?? DateTime.now()).toIso8601String().substring(0, 10);
  if (action.label == 'Create event') values['starts_on'] = today;
  if (action.label == 'Create shareable report') {
    values['period'] = today.substring(0, 7);
  }
  if (record != null) {
    for (final key in values.keys.toList()) {
      if (!record.containsKey(key)) continue;
      final value = record[key];
      if (values[key] is Map && value is Map) {
        values[key] = {
          for (final entry in (values[key] as Map).entries)
            entry.key: value[entry.key] ?? entry.value,
        };
      } else if (action.specFor(key)?.type == FieldType.boolean) {
        values[key] = value == true || value == 1;
      } else {
        values[key] = value ?? '';
      }
    }
  }
  return values;
}

/// Nested brand settings stay individual text fields, including colors/fonts.
Map<String, dynamic> flattenFormObject(Map values, [String prefix = '']) {
  final result = <String, dynamic>{};
  for (final entry in values.entries) {
    final key = prefix.isEmpty ? '${entry.key}' : '$prefix.${entry.key}';
    if (entry.value is Map) {
      result.addAll(flattenFormObject(entry.value as Map, key));
    } else {
      result[key] = entry.value;
    }
  }
  return result;
}

Map<String, dynamic> expandFormObject(Map<String, dynamic> values) {
  final result = <String, dynamic>{};
  for (final entry in values.entries) {
    final keys = entry.key.split('.');
    var target = result;
    for (final key in keys.take(keys.length - 1)) {
      target =
          target.putIfAbsent(key, () => <String, dynamic>{})
              as Map<String, dynamic>;
    }
    target[keys.last] = entry.value;
  }
  return result;
}
