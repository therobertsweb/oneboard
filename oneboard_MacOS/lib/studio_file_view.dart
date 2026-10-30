import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'apple_design.dart';
import 'board_api.dart';

bool isHtmlFile(String name) {
  final lower = name.toLowerCase();
  return lower.endsWith('.html') || lower.endsWith('.htm');
}

/// Short English labels for the assistant quick prompts shipped by the
/// backend (`quick_prompts` map keys).
String quickPromptLabel(String key) => switch (key) {
  'hero' => 'Document workspace',
  'section' => 'Suggest new file',
  'cta' => 'Review & fix',
  'landing' => 'Draft document',
  _ => key.replaceAll('_', ' '),
};

/// One-line summary of a team-shared folder (`team_context` map).
String teamShareLabel(Map<String, dynamic> teamContext) {
  final team = (teamContext['team'] as Map?)?.cast<String, dynamic>() ?? {};
  final name = team['name']?.toString() ?? 'Team';
  final role = teamContext['role']?.toString() ?? '';
  final permissions =
      (teamContext['permissions'] as Map?)?.cast<String, dynamic>() ?? {};
  final parts = ['Shared by $name'];
  if (role.isNotEmpty) parts.add(role);
  if (permissions['edit'] == false) parts.add('view only');
  return parts.join(' · ');
}

/// Thumbnail of an uploaded site image, fetched with the authenticated API.
class AssetThumb extends StatefulWidget {
  const AssetThumb({super.key, required this.api, required this.asset});

  final BoardApi api;
  final Map<String, dynamic> asset;

  @override
  State<AssetThumb> createState() => _AssetThumbState();
}

class _AssetThumbState extends State<AssetThumb> {
  late final Future<Uint8List?> _bytes;

  @override
  void initState() {
    super.initState();
    final path = widget.asset['path']?.toString() ?? '';
    _bytes = widget.api
        .getBytes(
          '/api/site-manager/assets/raw?path=${Uri.encodeQueryComponent(path)}',
        )
        .then<Uint8List?>((value) => value)
        .catchError((_) => null);
  }

  @override
  Widget build(BuildContext context) {
    final name = widget.asset['name']?.toString() ?? 'Image';
    final size = widget.asset['size_label']?.toString() ?? '';
    return SizedBox(
      width: 132,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            height: 88,
            decoration: BoxDecoration(
              color: const Color(0xFFF2F2F7),
              borderRadius: BorderRadius.circular(10),
            ),
            clipBehavior: Clip.antiAlias,
            child: FutureBuilder<Uint8List?>(
              future: _bytes,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(
                    child: SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  );
                }
                final bytes = snapshot.data;
                if (bytes == null || bytes.isEmpty) {
                  return const Center(
                    child: Icon(
                      Icons.broken_image_outlined,
                      color: boardMuted,
                    ),
                  );
                }
                return Image.memory(
                  bytes,
                  width: double.infinity,
                  height: 88,
                  fit: BoxFit.cover,
                  errorBuilder: (context, _, _) => const Center(
                    child: Icon(
                      Icons.broken_image_outlined,
                      color: boardMuted,
                    ),
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 5),
          Text(
            name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
          ),
          if (size.isNotEmpty)
            Text(
              size,
              style: const TextStyle(color: boardMuted, fontSize: 11),
            ),
        ],
      ),
    );
  }
}

/// File viewer for Studio. Loads `GET /api/site-manager?preview=<path>` and
/// renders text inline, images from `/api/site-manager/files/raw`, and HTML
/// source with a shortcut to the rendered Preview page.
class StudioFileView extends StatefulWidget {
  const StudioFileView({
    super.key,
    required this.api,
    required this.filePath,
    required this.displayName,
    required this.onOpenPreview,
  });

  final BoardApi api;
  final String filePath;
  final String displayName;
  final void Function(String path) onOpenPreview;

  @override
  State<StudioFileView> createState() => _StudioFileViewState();
}

class _StudioFileViewState extends State<StudioFileView> {
  late Future<_FilePreview> _previewFuture;

  @override
  void initState() {
    super.initState();
    _previewFuture = _load();
  }

  Future<_FilePreview> _load() async {
    final query = Uri.encodeQueryComponent(widget.filePath);
    final response = await widget.api.get('/api/site-manager?preview=$query');
    final manager = (response['manager'] as Map?)?.cast<String, dynamic>();
    final files = (manager?['files'] as Map?)?.cast<String, dynamic>();
    final preview =
        (files?['preview'] as Map?)?.cast<String, dynamic>() ?? {};
    Uint8List? imageBytes;
    if (preview['type'] == 'image') {
      imageBytes = await widget.api.getBytes(
        '/api/site-manager/files/raw?path=$query',
      );
    }
    return _FilePreview(
      type: preview['type']?.toString() ?? 'unsupported',
      content: preview['content']?.toString() ?? '',
      rawUrl: preview['raw_url']?.toString() ?? '',
      imageBytes: imageBytes,
    );
  }

  void _retry() => setState(() => _previewFuture = _load());

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: BoardBackdrop(
        child: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 14, 20, 6),
                child: Row(
                  children: [
                    IconButton(
                      tooltip: 'Back to files',
                      onPressed: () => Navigator.pop(context),
                      icon: const Icon(Icons.arrow_back_rounded),
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            widget.displayName,
                            style: const TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w700,
                              color: boardInk,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            widget.filePath,
                            style: const TextStyle(
                              fontSize: 12,
                              color: boardMuted,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(20, 10, 20, 24),
                  child: FutureBuilder<_FilePreview>(
                    future: _previewFuture,
                    builder: (context, snapshot) {
                      if (snapshot.connectionState != ConnectionState.done) {
                        return const Padding(
                          padding: EdgeInsets.all(48),
                          child: Center(child: CircularProgressIndicator()),
                        );
                      }
                      if (snapshot.hasError || !snapshot.hasData) {
                        return BoardSurface(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                'Could not open this file.',
                                style: TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.w600,
                                  color: boardInk,
                                ),
                              ),
                              const SizedBox(height: 8),
                              SelectableText(
                                '${snapshot.error ?? 'Unknown error'}'.replaceFirst(
                                  'Exception: ',
                                  '',
                                ),
                                style: const TextStyle(
                                  color: boardMuted,
                                  fontSize: 13,
                                ),
                              ),
                              const SizedBox(height: 14),
                              OutlinedButton.icon(
                                onPressed: _retry,
                                icon: const Icon(Icons.refresh_rounded, size: 16),
                                label: const Text('Retry'),
                              ),
                            ],
                          ),
                        );
                      }
                      return _previewBody(snapshot.data!);
                    },
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _previewBody(_FilePreview preview) {
    switch (preview.type) {
      case 'text':
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (isHtmlFile(widget.displayName))
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: BoardSurface(
                  child: Row(
                    children: [
                      const Expanded(
                        child: Text(
                          'This is the page source. Open Preview to see it rendered.',
                          style: TextStyle(color: boardMuted, fontSize: 13),
                        ),
                      ),
                      const SizedBox(width: 12),
                      FilledButton.icon(
                        onPressed: () {
                          Navigator.pop(context);
                          widget.onOpenPreview(widget.filePath);
                        },
                        icon: const Icon(Icons.visibility_outlined, size: 16),
                        label: const Text('Open in Preview'),
                      ),
                    ],
                  ),
                ),
              ),
            BoardSurface(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Contents (first 20,000 characters)',
                    style: TextStyle(color: boardMuted, fontSize: 12),
                  ),
                  const SizedBox(height: 10),
                  SelectableText(
                    preview.content.isEmpty
                        ? 'This file is empty.'
                        : preview.content,
                    style: const TextStyle(
                      color: boardInk,
                      fontSize: 12.5,
                      height: 1.6,
                      fontFamily: 'Menlo',
                      fontFamilyFallback: ['monospace'],
                    ),
                  ),
                ],
              ),
            ),
          ],
        );
      case 'image':
        final bytes = preview.imageBytes;
        if (bytes == null || bytes.isEmpty) {
          return const BoardSurface(
            child: Text(
              'The image could not be loaded.',
              style: TextStyle(color: boardMuted),
            ),
          );
        }
        return BoardSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Image.memory(bytes, fit: BoxFit.contain),
              ),
              const SizedBox(height: 10),
              Text(
                '${(bytes.lengthInBytes / 1024).toStringAsFixed(1)} KB',
                style: const TextStyle(color: boardMuted, fontSize: 12),
              ),
            ],
          ),
        );
      default:
        return BoardSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(
                    Icons.insert_drive_file_outlined,
                    color: boardMuted,
                  ),
                  SizedBox(width: 10),
                  Text(
                    'Preview is not available for this file type.',
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: boardInk,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              const Text(
                'Text files and images can be previewed here. Other files stay untouched in your connected folder.',
                style: TextStyle(color: boardMuted, fontSize: 13, height: 1.5),
              ),
              if (preview.rawUrl.isNotEmpty) ...[
                const SizedBox(height: 8),
                SelectableText(
                  preview.rawUrl,
                  style: const TextStyle(color: boardMuted, fontSize: 12),
                ),
              ],
            ],
          ),
        );
    }
  }
}

class _FilePreview {
  const _FilePreview({
    required this.type,
    required this.content,
    required this.rawUrl,
    this.imageBytes,
  });

  final String type;
  final String content;
  final String rawUrl;
  final Uint8List? imageBytes;
}
