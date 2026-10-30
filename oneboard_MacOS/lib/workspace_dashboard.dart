import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' show CupertinoIcons;
import 'apple_design.dart';
import 'search_console_panel.dart';

class WorkspaceDashboard extends StatelessWidget {
  const WorkspaceDashboard({
    super.key,
    required this.data,
    required this.userName,
    required this.onConnect,
    required this.onOpenStudio,
    required this.onNavigate,
    this.searchConsole,
  });
  final Map<String, dynamic> data;
  final Widget? searchConsole;
  final String userName;
  final VoidCallback onConnect, onOpenStudio;
  final ValueChanged<int> onNavigate;

  @override
  Widget build(BuildContext context) {
    final gsc = (data['gsc'] as Map?)?.cast<String, dynamic>() ?? {};
    final site = gsc['selected_site_url']?.toString();
    final name = userName.trim().split(' ').first;
    final hour = DateTime.now().hour;
    final greeting = hour < 12
        ? 'Good morning'
        : hour < 18
        ? 'Good afternoon'
        : 'Good evening';
    return ListView(
      children: [
        const Text(
          'YOUR SPACE, SIMPLIFIED',
          style: TextStyle(
            color: boardMuted,
            fontSize: 10,
            letterSpacing: 1.7,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '$greeting${name.isEmpty ? '' : ', $name'}.',
                    style: const TextStyle(
                      fontSize: 34,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -1.3,
                      color: boardInk,
                    ),
                  ),
                  const SizedBox(height: 9),
                  const Text(
                    'A little focus. A lot of possibility.',
                    style: TextStyle(fontSize: 15, color: boardMuted),
                  ),
                ],
              ),
            ),
            FilledButton.icon(
              onPressed: onConnect,
              icon: const Icon(CupertinoIcons.add, size: 18),
              label: const Text('Connect project'),
            ),
          ],
        ),
        const SizedBox(height: 30),
        Row(
          children: [
            Expanded(
              child: _metricCard(
                'Connected site',
                site == null || site.isEmpty ? 'Not connected' : site,
                CupertinoIcons.globe,
                const Color(0xFF348BFF),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: _metricCard(
                'Organic clicks',
                searchMetric(gsc, 0),
                CupertinoIcons.chart_bar,
                const Color(0xFF9374FA),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: _metricCard(
                'Impressions',
                searchMetric(gsc, 1),
                CupertinoIcons.eye,
                const Color(0xFF30BC80),
              ),
            ),
          ],
        ),
        const SizedBox(height: 30),
        if (searchConsole != null) ...[
          searchConsole!,
          const SizedBox(height: 30),
        ],
        LayoutBuilder(
          builder: (context, constraints) {
            final workspace = Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Text(
                      'Your workspace',
                      style: TextStyle(
                        fontSize: 19,
                        fontWeight: FontWeight.w600,
                        letterSpacing: -.4,
                      ),
                    ),
                    const Spacer(),
                    TextButton(
                      onPressed: onOpenStudio,
                      child: const Text('Open Studio'),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                BoardSurface(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: const Color(0xFFEBF1FF),
                              borderRadius: BorderRadius.circular(14),
                            ),
                            child: const Icon(
                              CupertinoIcons.device_desktop,
                              color: boardBlue,
                              size: 25,
                            ),
                          ),
                          const SizedBox(width: 15),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  site == null || site.isEmpty
                                      ? 'Bring your next project to life'
                                      : site,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w600,
                                    fontSize: 15,
                                  ),
                                ),
                                const SizedBox(height: 6),
                                const Text(
                                  'Your websites, content, and ideas. Together.',
                                  style: TextStyle(
                                    color: boardMuted,
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 23),
                      const Divider(height: 1, color: Color(0x0F243B70)),
                      const SizedBox(height: 19),
                      Row(
                        children: [
                          const Icon(
                            CupertinoIcons.folder,
                            size: 16,
                            color: boardMuted,
                          ),
                          const SizedBox(width: 8),
                          const Expanded(
                            child: Text(
                              'Connect a folder on this Mac to get started.',
                              style: TextStyle(color: boardMuted, fontSize: 12),
                            ),
                          ),
                          TextButton(
                            onPressed: onConnect,
                            child: const Text('Choose folder'),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 26),
                const Text(
                  'Make room for what matters',
                  style: TextStyle(
                    fontSize: 19,
                    fontWeight: FontWeight.w600,
                    letterSpacing: -.4,
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: BoardFeatureTile(
                        title: 'Plan ahead',
                        subtitle: 'Make your next move.',
                        icon: CupertinoIcons.calendar,
                        color: const Color(0xFFF47B69),
                        onTap: () => onNavigate(6),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: BoardFeatureTile(
                        title: 'Create & share',
                        subtitle: 'Give your ideas a voice.',
                        icon: CupertinoIcons.pencil_outline,
                        color: const Color(0xFF8A70EC),
                        onTap: () => onNavigate(10),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: BoardFeatureTile(
                        title: 'Better together',
                        subtitle: 'Bring your team along.',
                        icon: CupertinoIcons.person_2,
                        color: boardBlue,
                        onTap: () => onNavigate(11),
                      ),
                    ),
                  ],
                ),
              ],
            );
            if (constraints.maxWidth < 900) return workspace;
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: workspace),
                const SizedBox(width: 24),
                SizedBox(
                  width: 260,
                  child: Padding(
                    padding: const EdgeInsets.only(top: 48),
                    child: BoardInspiration(onOpen: onOpenStudio),
                  ),
                ),
              ],
            );
          },
        ),
        const SizedBox(height: 24),
      ],
    );
  }

  Widget _metricCard(String label, String value, IconData icon, Color color) =>
      Container(
        height: 154,
        padding: const EdgeInsets.all(22),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [color, Color.lerp(color, const Color(0xFF303BDC), .28)!],
          ),
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: .18),
              blurRadius: 18,
              offset: const Offset(0, 6),
            ),
          ],
          border: Border.all(color: Colors.white.withValues(alpha: .35)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: Colors.white.withValues(alpha: .9), size: 23),
            const Spacer(),
            Text(
              label,
              style: TextStyle(
                color: Colors.white.withValues(alpha: .85),
                fontSize: 12,
              ),
            ),
            const SizedBox(height: 5),
            Text(
              value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: label == 'Connected site' ? 19 : 29,
                fontWeight: FontWeight.w600,
                letterSpacing: -.6,
                color: Colors.white,
              ),
            ),
          ],
        ),
      );
}
