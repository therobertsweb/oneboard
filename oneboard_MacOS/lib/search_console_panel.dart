import 'package:flutter/material.dart';
import 'apple_design.dart';

String searchMetric(Map<String, dynamic> data, int index) {
  final stats = data['stats'];
  if (data['connected'] != true || stats is! List || stats.length <= index) {
    return '—';
  }
  return (stats[index] as Map)['value']?.toString() ?? '—';
}

/// Strips endpoint URLs from backend errors so the user never sees them.
String friendlySearchError(String raw) {
  return raw
      .replaceAll(RegExp(r'https?://\S+'), 'the registered address')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
}

class SearchConsolePanel extends StatelessWidget {
  const SearchConsolePanel({
    super.key,
    required this.data,
    this.busy = false,
    this.onConnect,
    this.onDisconnect,
    this.onRefresh,
    this.onSelectProperty,
    this.onCreatePage,
  });
  final Map<String, dynamic> data;
  final bool busy;
  final VoidCallback? onConnect, onDisconnect, onRefresh;
  final ValueChanged<String>? onSelectProperty;
  final ValueChanged<Map<String, dynamic>>? onCreatePage;

  List<Map<String, dynamic>> rows(String key) => (data[key] as List? ?? [])
      .whereType<Map>()
      .map((e) => e.cast<String, dynamic>())
      .toList();

  @override
  Widget build(BuildContext context) {
    final connected = data['connected'] == true;
    final properties = rows('sites')
        .where((s) => s['permissionLevel'] != 'siteUnverifiedUser')
        .map((s) => s['siteUrl'].toString())
        .toSet();
    final selected = data['selected_site_url']?.toString();
    final range = data['date_range'] as Map? ?? {};
    return BoardSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  'Google Search Console',
                  style: TextStyle(fontSize: 21, fontWeight: FontWeight.w600),
                ),
              ),
              if (connected)
                TextButton(
                  onPressed: busy ? null : onRefresh,
                  child: const Text('Refresh'),
                ),
              TextButton(
                onPressed: busy
                    ? null
                    : connected
                    ? onDisconnect
                    : onConnect,
                child: Text(connected ? 'Disconnect' : 'Connect Google'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            connected
                ? '${range['start'] ?? ''} – ${range['end'] ?? ''} · Search performance'
                : 'Connect Google to see how people discover your website.',
            style: const TextStyle(color: boardMuted),
          ),
          if (data['configured'] != true)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: Text(
                'Google OAuth needs to be configured before you can connect.',
              ),
            ),
          if (data['error'] != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: SelectableText(
                friendlySearchError(data['error'].toString()),
                style: const TextStyle(color: Colors.red),
              ),
            ),
          if (connected) ...[
            const SizedBox(height: 20),
            DropdownButtonFormField<String>(
              initialValue: properties.contains(selected) ? selected : null,
              key: ValueKey(selected),
              isExpanded: true,
              decoration: InputDecoration(
                labelText: data['site_scoped'] == true
                    ? 'Property for this project'
                    : 'Search property',
              ),
              items: properties
                  .map(
                    (p) => DropdownMenuItem(
                      value: p,
                      child: Text(p, overflow: TextOverflow.ellipsis),
                    ),
                  )
                  .toList(),
              onChanged: busy
                  ? null
                  : (value) {
                      if (value != null) onSelectProperty?.call(value);
                    },
            ),
            if (properties.isEmpty)
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: Text(
                  'No verified properties found for this Google account.',
                ),
              ),
            const SizedBox(height: 20),
            Wrap(
              spacing: 32,
              runSpacing: 16,
              children: [
                for (final entry in [
                  'Clicks',
                  'Impressions',
                  'CTR',
                  'Average position',
                ].asMap().entries)
                  SizedBox(
                    width: 150,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          entry.value,
                          style: const TextStyle(color: boardMuted),
                        ),
                        Text(
                          searchMetric(data, entry.key),
                          style: const TextStyle(
                            fontSize: 27,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 24),
            _chart('Top queries · clicks', rows('query_chart')),
            _chart('Top pages · impressions', rows('page_chart')),
            if (rows('seo_opportunities').isNotEmpty) ...[
              const Text(
                'SEO opportunities',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              for (final item in rows('seo_opportunities'))
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${item['title'] ?? item['keyword']}'),
                  subtitle: Text(
                    '${item['keyword']} · ${item['impressions']} impressions · Position ${item['position']}',
                  ),
                  trailing: OutlinedButton(
                    onPressed: busy || onCreatePage == null
                        ? null
                        : () => onCreatePage!(item),
                    child: const Text('Create page'),
                  ),
                ),
              const SizedBox(height: 20),
            ],
            _table('Search queries', rows('queries')),
            _table('Pages', rows('pages')),
          ],
        ],
      ),
    );
  }

  Widget _chart(String title, List<Map<String, dynamic>> items) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
      const SizedBox(height: 12),
      for (final item in items)
        Padding(
          padding: const EdgeInsets.only(bottom: 14),
          child: Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${item['label']}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Text('${item['display'] ?? item['value']}'),
                ],
              ),
              const SizedBox(height: 6),
              LinearProgressIndicator(
                value: ((num.tryParse('${item['pct']}') ?? 0) / 100)
                    .clamp(0, 1)
                    .toDouble(),
                minHeight: 6,
                borderRadius: BorderRadius.circular(6),
                color: boardBlue,
                backgroundColor: const Color(0xFFEDF1FA),
              ),
            ],
          ),
        ),
      if (items.isEmpty)
        const Text(
          'No search data for this period.',
          style: TextStyle(color: boardMuted),
        ),
      const SizedBox(height: 20),
    ],
  );

  Widget _table(
    String title,
    List<Map<String, dynamic>> items,
  ) => ExpansionTile(
    tilePadding: EdgeInsets.zero,
    title: Text('$title (${items.length})'),
    children: [
      if (items.isEmpty)
        const ListTile(title: Text('No search data for this period.')),
      if (items.isNotEmpty)
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
            columns: [
              title,
              'Clicks',
              'Impressions',
              'CTR',
              'Position',
            ].map((s) => DataColumn(label: Text(s))).toList(),
            rows: items
                .map(
                  (item) => DataRow(
                    cells: ['key', 'clicks', 'impressions', 'ctr', 'position']
                        .map(
                          (key) => DataCell(
                            key == 'key'
                                ? SizedBox(
                                    width: 320,
                                    child: SelectableText('${item[key] ?? ''}'),
                                  )
                                : Text('${item[key] ?? ''}'),
                          ),
                        )
                        .toList(),
                  ),
                )
                .toList(),
          ),
        ),
    ],
  );
}
