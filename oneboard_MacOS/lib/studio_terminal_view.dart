import 'package:flutter/material.dart';

import 'apple_design.dart';

/// Extracts the terminal block from an action result, when present.
///
/// Backend shape: `{command, cwd, exit_code, output, started_at}`.
Map<String, dynamic>? terminalOf(Map<String, dynamic> result) {
  final terminal = result['terminal'];
  if (terminal is! Map) return null;
  final map = terminal.cast<String, dynamic>();
  if (map['output'] == null && map['command'] == null) return null;
  return map;
}

/// Short human-readable status for an action result (`ok: true/false`).
String resultStatusLabel(Map<String, dynamic> result) =>
    result['ok'] == false ? 'Needs attention' : 'Done';

final _linkPattern = RegExp("https?://[^\\s'\"<>]+");

/// Collects http(s) links anywhere inside an action result (share links,
/// report URLs, uploaded files), deduplicated and capped.
List<String> findLinks(dynamic value, {int limit = 10}) {
  final found = <String>[];
  void visit(dynamic node) {
    if (found.length >= limit) return;
    if (node is String) {
      for (final match in _linkPattern.allMatches(node)) {
        final link = match.group(0)!;
        if (!found.contains(link)) found.add(link);
        if (found.length >= limit) return;
      }
    } else if (node is Map) {
      for (final entry in node.entries) {
        visit(entry.value);
        if (found.length >= limit) return;
      }
    } else if (node is List) {
      for (final item in node) {
        visit(item);
        if (found.length >= limit) return;
      }
    }
  }

  visit(value);
  return found;
}

/// Dark terminal card rendering a backend terminal block.
class TerminalResultView extends StatelessWidget {
  const TerminalResultView({super.key, required this.terminal});

  final Map<String, dynamic> terminal;

  @override
  Widget build(BuildContext context) {
    final command = terminal['command']?.toString() ?? '';
    final cwd = terminal['cwd']?.toString() ?? '';
    final output = terminal['output']?.toString() ?? '';
    final startedAt = terminal['started_at']?.toString() ?? '';
    final exitCode = terminal['exit_code'];
    final exitOk = exitCode == 0;
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(14),
      ),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.terminal_rounded,
                size: 16,
                color: Colors.white70,
              ),
              const SizedBox(width: 8),
              const Text(
                'Terminal',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 9,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: (exitOk ? Colors.green : Colors.red).withValues(
                    alpha: .18,
                  ),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  'Exit ${exitCode ?? '?'}',
                  style: TextStyle(
                    color: exitOk
                        ? const Color(0xFF7EE2A8)
                        : const Color(0xFFFF9D9D),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          if (command.isNotEmpty) ...[
            const SizedBox(height: 10),
            SelectableText(
              '\$ $command',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 12.5,
                fontFamily: 'Menlo',
                fontFamilyFallback: ['monospace'],
              ),
            ),
          ],
          if (cwd.isNotEmpty || startedAt.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              [cwd, startedAt].where((part) => part.isNotEmpty).join(' · '),
              style: const TextStyle(color: Colors.white54, fontSize: 11),
            ),
          ],
          if (output.isNotEmpty) ...[
            const SizedBox(height: 10),
            Container(
              width: double.infinity,
              constraints: const BoxConstraints(maxHeight: 320),
              child: SingleChildScrollView(
                child: SelectableText(
                  output,
                  style: const TextStyle(
                    color: Color(0xFFE8E8EA),
                    fontSize: 12.5,
                    height: 1.55,
                    fontFamily: 'Menlo',
                    fontFamilyFallback: ['monospace'],
                  ),
                ),
              ),
            ),
          ],
          if (output.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text(
                'The command produced no output.',
                style: TextStyle(color: Colors.white54, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }
}

/// Card shown after an action runs: a status line, a terminal block when the
/// result carries one, short text highlights, and the raw payload on demand.
class ActionResultCard extends StatelessWidget {
  const ActionResultCard({
    super.key,
    required this.result,
    required this.detailsBuilder,
    this.onOpenLink,
  });

  final Map<String, dynamic> result;
  final Widget Function(dynamic value) detailsBuilder;
  final void Function(String url)? onOpenLink;

  static const _highlightKeys = <String>[
    'message',
    'summary',
    'notification',
    'output_text',
    'response',
  ];

  @override
  Widget build(BuildContext context) {
    final terminal = terminalOf(result);
    final highlights = <String>[];
    for (final key in _highlightKeys) {
      final value = result[key];
      if (value is String && value.trim().isNotEmpty) {
        highlights.add(value.trim());
      }
    }
    final run = result['run'];
    final snippet = result['snippet'];
    final links = findLinks(result);
    final rest = Map<String, dynamic>.from(result)
      ..remove('terminal')
      ..remove('manager');
    return BoardSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                result['ok'] == false
                    ? Icons.error_outline_rounded
                    : Icons.check_circle_outline_rounded,
                size: 18,
                color: result['ok'] == false
                    ? const Color(0xFFB33142)
                    : const Color(0xFF1F9D55),
              ),
              const SizedBox(width: 8),
              Text(
                resultStatusLabel(result),
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  color: boardInk,
                ),
              ),
            ],
          ),
          for (final highlight in highlights) ...[
            const SizedBox(height: 10),
            SelectableText(
              highlight,
              style: const TextStyle(
                color: boardInk,
                fontSize: 13,
                height: 1.5,
              ),
            ),
          ],
          if (run is Map && run.isNotEmpty) ...[
            const SizedBox(height: 10),
            detailsBuilder(run),
          ],
          if (snippet is String && snippet.trim().isNotEmpty) ...[
            const SizedBox(height: 10),
            const Text(
              'Embed code',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: boardInk,
              ),
            ),
            const SizedBox(height: 6),
            Container(
              width: double.infinity,
              constraints: const BoxConstraints(maxHeight: 220),
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: const Color(0xFFF9F9FB),
                borderRadius: BorderRadius.circular(8),
              ),
              child: SingleChildScrollView(
                child: SelectableText(
                  snippet,
                  style: const TextStyle(
                    fontSize: 12,
                    height: 1.55,
                    fontFamily: 'Menlo',
                    fontFamilyFallback: ['monospace'],
                  ),
                ),
              ),
            ),
          ],
          if (terminal != null) ...[
            const SizedBox(height: 12),
            TerminalResultView(terminal: terminal),
          ],
          if (links.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Text(
              'Links',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: boardInk,
              ),
            ),
            const SizedBox(height: 6),
            for (final link in links)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  children: [
                    Expanded(
                      child: SelectableText(
                        link,
                        style: const TextStyle(
                          color: boardBlue,
                          fontSize: 12,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    OutlinedButton(
                      onPressed: onOpenLink == null
                          ? null
                          : () => onOpenLink!(link),
                      child: const Text('Open'),
                    ),
                  ],
                ),
              ),
          ],
          if (rest.isNotEmpty) ...[
            const SizedBox(height: 6),
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              childrenPadding: EdgeInsets.zero,
              shape: const Border(),
              collapsedShape: const Border(),
              title: const Text(
                'Details',
                style: TextStyle(fontSize: 13, color: boardMuted),
              ),
              children: [detailsBuilder(rest)],
            ),
          ],
        ],
      ),
    );
  }
}
