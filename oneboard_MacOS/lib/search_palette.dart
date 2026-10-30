import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'apple_design.dart';
import 'feature_catalog.dart';
import 'workspace_chrome.dart';

/// A single search result: either a navigation section or a catalog action.
class PaletteEntry {
  const PaletteEntry({
    required this.kind,
    required this.section,
    required this.title,
    required this.subtitle,
    this.action,
  });

  /// 'section' or 'action'.
  final String kind;
  final int section;
  final String title;
  final String subtitle;
  final FeatureAction? action;
}

/// All searchable entries: every sidebar section plus every catalog action.
List<PaletteEntry> allPaletteEntries() {
  final entries = <PaletteEntry>[];
  for (var index = 0; index < workspaceNavigation.length; index++) {
    entries.add(
      PaletteEntry(
        kind: 'section',
        section: index,
        title: workspaceNavigation[index].title,
        subtitle: 'Go to section',
      ),
    );
  }
  for (var pageIndex = 0; pageIndex < featurePages.length; pageIndex++) {
    final page = featurePages[pageIndex];
    for (final action in page.actions) {
      entries.add(
        PaletteEntry(
          kind: 'action',
          section: pageIndex + 1,
          title: action.label,
          subtitle: page.title,
          action: action,
        ),
      );
    }
  }
  return entries;
}

int _rank(String query, PaletteEntry entry) {
  final q = query.toLowerCase();
  final title = entry.title.toLowerCase();
  final subtitle = entry.subtitle.toLowerCase();
  if (title == q) return 0;
  if (title.startsWith(q)) return entry.kind == 'section' ? 1 : 2;
  if (title.contains(q)) return entry.kind == 'section' ? 3 : 4;
  if (subtitle.contains(q)) return 5;
  return 6;
}

/// Filters and ranks entries for [query]. Empty query returns sections only.
List<PaletteEntry> searchPaletteEntries(String query, {int limit = 9}) {
  final entries = allPaletteEntries();
  final q = query.trim().toLowerCase();
  if (q.isEmpty) {
    return entries.where((e) => e.kind == 'section').take(limit).toList();
  }
  final scored = <(int, PaletteEntry)>[];
  for (final entry in entries) {
    final rank = _rank(q, entry);
    if (rank < 6) scored.add((rank, entry));
  }
  scored.sort((a, b) {
    final byRank = a.$1.compareTo(b.$1);
    if (byRank != 0) return byRank;
    return a.$2.title.compareTo(b.$2.title);
  });
  return scored.map((s) => s.$2).take(limit).toList(growable: false);
}

/// Spotlight-style search palette over sections and actions.
class SearchPalette extends StatefulWidget {
  const SearchPalette({
    super.key,
    required this.onPickSection,
    required this.onPickAction,
  });

  final ValueChanged<int> onPickSection;
  final void Function(int section, FeatureAction action) onPickAction;

  @override
  State<SearchPalette> createState() => _SearchPaletteState();
}

class _SearchPaletteState extends State<SearchPalette> {
  final _controller = TextEditingController();
  final _focusNode = FocusNode();
  var _selected = 0;
  var _results = searchPaletteEntries('');

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _onQueryChanged(String value) {
    setState(() {
      _results = searchPaletteEntries(value);
      _selected = 0;
    });
  }

  void _move(int delta) {
    if (_results.isEmpty) return;
    setState(() {
      _selected = (_selected + delta) % _results.length;
    });
  }

  void _pick(PaletteEntry entry) {
    Navigator.pop(context);
    if (entry.kind == 'section' || entry.action == null) {
      widget.onPickSection(entry.section);
    } else {
      widget.onPickAction(entry.section, entry.action!);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: SizedBox(
        width: 520,
        child: CallbackShortcuts(
          bindings: {
            const SingleActivator(LogicalKeyboardKey.arrowDown): () => _move(1),
            const SingleActivator(LogicalKeyboardKey.arrowUp): () => _move(-1),
            const SingleActivator(LogicalKeyboardKey.enter): () {
              if (_results.isNotEmpty) _pick(_results[_selected]);
            },
          },
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
                child: TextField(
                  controller: _controller,
                  focusNode: _focusNode,
                  autofocus: true,
                  onChanged: _onQueryChanged,
                  onSubmitted: (_) {
                    if (_results.isNotEmpty) _pick(_results[_selected]);
                  },
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.search_rounded, size: 18),
                    hintText: 'Search sections and actions…',
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.all(Radius.circular(10)),
                      borderSide: BorderSide.none,
                    ),
                    filled: true,
                    fillColor: Color(0xFFF1F3F8),
                    contentPadding: EdgeInsets.symmetric(vertical: 12),
                  ),
                ),
              ),
              Flexible(
                child: ListView.builder(
                  shrinkWrap: true,
                  padding: const EdgeInsets.fromLTRB(8, 0, 8, 10),
                  itemCount: _results.length,
                  itemBuilder: (context, index) {
                    final entry = _results[index];
                    final selected = index == _selected;
                    return Material(
                      color: selected
                          ? boardBlue.withValues(alpha: .1)
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(8),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(8),
                        onTap: () => _pick(entry),
                        onHover: (_) {
                          if (!selected) setState(() => _selected = index);
                        },
                        child: Padding(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 9,
                          ),
                          child: Row(
                            children: [
                              Icon(
                                entry.kind == 'section'
                                    ? Icons.folder_open_outlined
                                    : Icons.bolt_outlined,
                                size: 16,
                                color: selected ? boardBlue : boardMuted,
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: Text(
                                  entry.title,
                                  style: TextStyle(
                                    fontSize: 13,
                                    fontWeight: selected
                                        ? FontWeight.w600
                                        : FontWeight.w400,
                                    color: boardInk,
                                  ),
                                ),
                              ),
                              Text(
                                entry.subtitle,
                                style: const TextStyle(
                                  fontSize: 11,
                                  color: boardMuted,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
