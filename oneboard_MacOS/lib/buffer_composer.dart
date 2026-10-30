import 'dart:io';

import 'package:flutter/material.dart';

import 'apple_design.dart';
import 'board_api.dart';

/// Short resolved state label for the attached social image.
String socialImageStateLabel({
  required bool hasImage,
  required bool generated,
  bool pending = false,
}) {
  if (!hasImage) return 'No image attached';
  if (pending) return 'Preview only';
  return generated ? 'AI image attached' : 'Image attached';
}

/// Notice shown when an image is ready locally but the media mirror failed.
/// The image itself is safe in the library; only the public copy is missing.
String mediaPendingNotice(String backendError) {
  final detail = backendError.replaceFirst('Exception: ', '');
  return 'Image saved to your library, but it cannot travel with the post yet. $detail';
}

/// Error shown when publishing with an image whose public copy is missing.
String mediaPublishBlockedNotice(String backendError) {
  final detail = backendError.replaceFirst('Exception: ', '');
  return 'The post was not sent because the image has no public copy yet. $detail Or remove the image to publish text only.';
}

/// Diagnosis title for a failed Buffer channel load, so the user can tell a
/// missing key apart from a rejected one.
String bufferDiagnosisTitle({required bool keyConfigured}) {
  return keyConfigured
      ? 'Buffer rejected the saved key'
      : 'Buffer is not connected';
}

/// Diagnosis detail for a failed Buffer channel load.
String bufferDiagnosisDetail({required bool keyConfigured, required String backendError}) {
  if (keyConfigured) {
    return 'A Buffer key is saved in this app, but Buffer answered with an '
        'error: $backendError Update the key in Settings and retry.';
  }
  return 'Save your Buffer key in Settings first. Keys are stored locally on '
      'this Mac, so a key saved on another machine or on the web is not reused here. '
      'Buffer answered: $backendError';
}

/// Payload for POST /api/social/images/edit. The URL must be the backend
/// library URL, never the Firebase mirror, so the service can resolve it.
Map<String, String> socialImageEditPayload(String imageUrl, String instruction) {
  return {'image_url': imageUrl.trim(), 'instruction': instruction.trim()};
}

/// Normalizes suggestion/idea items from /api/social/suggestions and
/// /api/social/ideas into a stable {title, prompt} shape.
List<Map<String, String>> parseSuggestionItems(dynamic raw) {
  if (raw is! List) return const [];
  return raw
      .whereType<Map>()
      .map(
        (item) => <String, String>{
          'title': '${item['title'] ?? 'Post idea'}',
          'prompt': '${item['prompt'] ?? ''}',
        },
      )
      .where((item) => item['prompt']!.isNotEmpty)
      .toList(growable: false);
}

String channelLabel(Map<String, dynamic> channel) {
  final name =
      channel['name']?.toString() ??
      channel['id']?.toString() ??
      'Channel';
  final suffix = [
    channel['service']?.toString() ?? '',
    channel['organization_name']?.toString() ?? '',
  ].where((part) => part.isNotEmpty).join(' · ');
  return suffix.isEmpty ? name : '$name ($suffix)';
}

Map<String, dynamic> bufferPostPayload({
  required List<String> channelIds,
  required String text,
  String postType = 'post',
  bool draft = true,
  bool publishNow = false,
  String? imageUrl,
  String? workspacePath,
}) => {
  'channel_ids': channelIds,
  'text': text.trim(),
  'post_type': postType,
  'draft': draft,
  'publish_now': publishNow,
  if (imageUrl != null && imageUrl.isNotEmpty) 'image_url': imageUrl,
  if (workspacePath != null && workspacePath.isNotEmpty)
    'expected_directory_path': workspacePath,
};

/// Visual Buffer composer: connected channels, site-based post ideas, AI text,
/// AI image generation, uploads, and AI edits shared through the owner's
/// media server, preview, and draft/queue/publish.
class BufferPanel extends StatefulWidget {
  const BufferPanel({
    super.key,
    required this.api,
    required this.workspacePath,
    required this.pickImage,
    required this.onOpenSettings,
    this.onPublished,
  });

  final BoardApi api;
  final String workspacePath;
  final Future<String?> Function() pickImage;
  final VoidCallback onOpenSettings;
  final void Function(Map<String, dynamic> result)? onPublished;

  @override
  State<BufferPanel> createState() => _BufferPanelState();
}

class _BufferLoadError implements Exception {
  const _BufferLoadError(this.message, {required this.keyConfigured});

  final String message;
  final bool keyConfigured;

  @override
  String toString() => message;
}

class _BufferLoad {
  const _BufferLoad({required this.channels, required this.keyConfigured});

  final List<Map<String, dynamic>> channels;
  final bool keyConfigured;
}

class _BufferPanelState extends State<BufferPanel> {
  late Future<_BufferLoad> _channelsFuture;
  late final TextEditingController _textController;
  late final TextEditingController _promptController;
  late final TextEditingController _imagePromptController;
  late final TextEditingController _imageEditController;
  final _selectedChannels = <String>{};
  String _postType = 'post';
  bool _draft = true;
  bool _publishNow = false;
  String? _localImagePath;
  String? _imageUrl;
  String? _libraryImageUrl;
  bool _imageGenerated = false;
  bool _uploadingImage = false;
  bool _generatingImage = false;
  bool _editingImage = false;
  bool _generating = false;
  bool _busy = false;
  String? _error;
  String? _notice;
  List<Map<String, String>> _suggestions = const [];
  String _siteName = '';
  bool _suggestionsLoading = true;
  bool _ideasBusy = false;
  String? _suggestionsError;

  @override
  void initState() {
    super.initState();
    _textController = TextEditingController();
    _promptController = TextEditingController();
    _imagePromptController = TextEditingController();
    _imageEditController = TextEditingController();
    _channelsFuture = _loadChannels();
    _loadSuggestions();
  }

  @override
  void dispose() {
    _textController.dispose();
    _promptController.dispose();
    _imagePromptController.dispose();
    _imageEditController.dispose();
    super.dispose();
  }

  Future<_BufferLoad> _loadChannels() async {
    var keyConfigured = false;
    try {
      final settings = await widget.api.get('/api/settings');
      final account = (settings['account'] as Map?) ?? const {};
      keyConfigured = account['buffer_api_key_configured'] == true;
    } catch (_) {
      keyConfigured = false;
    }
    try {
      final response = await widget.api.get('/api/social/buffer/channels');
      final channels = (response['channels'] as List?) ?? [];
      return _BufferLoad(
        channels: channels
            .whereType<Map>()
            .map((c) => c.cast<String, dynamic>())
            .toList(),
        keyConfigured: keyConfigured,
      );
    } catch (error) {
      Error.throwWithStackTrace(
        _BufferLoadError(error.toString(), keyConfigured: keyConfigured),
        StackTrace.current,
      );
    }
  }

  void _retryChannels() => setState(() => _channelsFuture = _loadChannels());

  Future<void> _loadSuggestions() async {
    setState(() {
      _suggestionsLoading = true;
      _suggestionsError = null;
    });
    try {
      final query = widget.workspacePath.isEmpty
          ? ''
          : '?expected_directory_path=${Uri.encodeQueryComponent(widget.workspacePath)}';
      final data = await widget.api.get('/api/social/suggestions$query');
      if (!mounted) return;
      setState(() {
        _suggestions = parseSuggestionItems(data['suggestions']);
        _siteName = data['site_name']?.toString() ?? '';
        _suggestionsLoading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _suggestions = const [];
        _suggestionsError = error.toString().replaceFirst('Exception: ', '');
        _suggestionsLoading = false;
      });
    }
  }

  Future<void> _generateIdeas() async {
    if (_ideasBusy) return;
    setState(() {
      _ideasBusy = true;
      _suggestionsError = null;
    });
    try {
      final data = await widget.api.post('/api/social/ideas', {
        'hint': _promptController.text.trim(),
        if (widget.workspacePath.isNotEmpty)
          'expected_directory_path': widget.workspacePath,
      });
      if (!mounted) return;
      setState(() {
        _suggestions = parseSuggestionItems(data['ideas']);
        if (data['site_name'] != null) {
          _siteName = data['site_name'].toString();
        }
      });
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _suggestionsError = error.toString().replaceFirst(
          'Exception: ',
          '',
        ),
      );
    } finally {
      if (mounted) setState(() => _ideasBusy = false);
    }
  }

  Future<void> _generateText() async {
    final prompt = _promptController.text.trim();
    if (_generating) return;
    setState(() {
      _generating = true;
      _error = null;
      _notice = null;
    });
    try {
      final result = await widget.api.post('/api/social/generate', {
        'prompt': prompt,
        if (widget.workspacePath.isNotEmpty)
          'expected_directory_path': widget.workspacePath,
      });
      if (!mounted) return;
      setState(() {
        _textController.text = result['text']?.toString() ?? '';
        if (result['from_site'] == true) {
          _notice = 'Written from your connected site context.';
        }
      });
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _error = error.toString().replaceFirst('Exception: ', ''),
      );
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  Future<void> _chooseImage() async {
    final path = await widget.pickImage();
    if (path == null || !mounted) return;
    await _attachLocalImage(path, generated: false);
  }

  bool get _imageBusy => _uploadingImage || _generatingImage || _editingImage;

  Future<void> _generateImage() async {
    final prompt = _imagePromptController.text.trim();
    if (prompt.isEmpty || _imageBusy) return;
    setState(() {
      _generatingImage = true;
      _error = null;
      _notice = null;
    });
    try {
      final data = await widget.api.post('/api/ai/images', {'prompt': prompt});
      final image = (data['image'] as Map?) ?? const {};
      final url = image['url']?.toString() ?? '';
      if (url.isEmpty) {
        throw Exception('The image service returned no image.');
      }
      await _attachLibraryImage(url, generated: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString().replaceFirst('Exception: ', '');
      });
    } finally {
      if (mounted) setState(() => _generatingImage = false);
    }
  }

  Future<void> _editImage() async {
    final instruction = _imageEditController.text.trim();
    final source = _libraryImageUrl ?? '';
    if (instruction.isEmpty || source.isEmpty || _imageBusy) return;
    setState(() {
      _editingImage = true;
      _error = null;
      _notice = null;
    });
    try {
      final data = await widget.api.post(
        '/api/social/images/edit',
        socialImageEditPayload(source, instruction),
      );
      final image = (data['image'] as Map?) ?? const {};
      final url = image['url']?.toString() ?? '';
      if (url.isEmpty) {
        throw Exception('The image service returned no image.');
      }
      if (!mounted) return;
      _imageEditController.clear();
      await _attachLibraryImage(url, generated: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString().replaceFirst('Exception: ', '');
      });
    } finally {
      if (mounted) setState(() => _editingImage = false);
    }
  }

  /// Downloads a backend library image, previews it locally, and mirrors it
  /// to the owner's media server, because Buffer cannot download loopback
  /// URLs.
  Future<void> _attachLibraryImage(String libraryUrl, {required bool generated}) async {
    final bytes = await widget.api.getBytes(libraryUrl);
    final tempDir = await Directory.systemTemp.createTemp('oneboard-social');
    final tempPath = '${tempDir.path}/ai-image.png';
    await File(tempPath).writeAsBytes(bytes, flush: true);
    String? publicUrl;
    String? mirrorError;
    try {
      publicUrl = await _mirrorLibraryImage(libraryUrl);
    } catch (error) {
      mirrorError = error.toString();
    }
    if (!mounted) return;
    setState(() {
      _localImagePath = tempPath;
      _libraryImageUrl = libraryUrl;
      _imageUrl = publicUrl;
      _imageGenerated = generated;
      _notice = publicUrl != null
          ? 'AI image ready. Buffer downloads the public copy from your media server.'
          : mediaPendingNotice(mirrorError ?? '');
    });
  }

  /// Asks the local backend to publish a library image to the media server.
  Future<String> _mirrorLibraryImage(String libraryUrl) async {
    final data = await widget.api.post('/api/social/images/mirror', {
      'image_url': libraryUrl,
    });
    final url = data['url']?.toString() ?? '';
    if (url.isEmpty) {
      throw Exception('The media server returned no public URL.');
    }
    return url;
  }

  /// Registers a local file with the backend library and mirrors it to the
  /// owner's media server, because Buffer cannot download loopback URLs.
  Future<void> _attachLocalImage(String path, {required bool generated}) async {
    setState(() {
      _localImagePath = path;
      _imageUrl = null;
      _libraryImageUrl = null;
      _imageGenerated = generated;
      _error = null;
      _notice = null;
      _uploadingImage = true;
    });
    try {
      final data = await widget.api.upload(
        '/api/social/images/upload',
        'image',
        path,
      );
      final image = (data['image'] as Map?) ?? const {};
      final libraryUrl = image['url']?.toString() ?? '';
      if (libraryUrl.isEmpty) {
        throw Exception('The image service returned no image.');
      }
      String? publicUrl;
      String? mirrorError;
      try {
        publicUrl = await _mirrorLibraryImage(libraryUrl);
      } catch (error) {
        mirrorError = error.toString();
      }
      if (!mounted) return;
      setState(() {
        _imageUrl = publicUrl;
        _libraryImageUrl = libraryUrl;
        _notice = publicUrl != null
            ? 'Image ready. Buffer downloads the public copy from your media server.'
            : mediaPendingNotice(mirrorError ?? '');
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _imageUrl = null;
        _libraryImageUrl = null;
        _error = error.toString().replaceFirst('Exception: ', '');
      });
    } finally {
      if (mounted) setState(() => _uploadingImage = false);
    }
  }

  void _removeImage() {
    setState(() {
      _localImagePath = null;
      _imageUrl = null;
      _libraryImageUrl = null;
      _imageGenerated = false;
    });
  }

  Future<void> _submit() async {
    final text = _textController.text.trim();
    if (_selectedChannels.isEmpty || text.isEmpty || _busy) return;
    if (_publishNow) {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Publish now?'),
          content: Text(
            'This will publish immediately to ${_selectedChannels.length} '
            'channel${_selectedChannels.length == 1 ? '' : 's'}.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Publish'),
            ),
          ],
        ),
      );
      if (confirmed != true || !mounted) return;
    }
    if (_libraryImageUrl != null && _imageUrl == null) {
      // The media server may have been configured after attaching.
      setState(() {
        _busy = true;
        _error = null;
        _notice = null;
      });
      try {
        final publicUrl = await _mirrorLibraryImage(_libraryImageUrl!);
        if (!mounted) return;
        setState(() => _imageUrl = publicUrl);
      } catch (error) {
        if (!mounted) return;
        setState(() {
          _busy = false;
          _error = mediaPublishBlockedNotice(error.toString());
        });
        return;
      }
    }
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      final result = await widget.api.post(
        '/api/social/buffer/posts',
        bufferPostPayload(
          channelIds: _selectedChannels.toList(),
          text: text,
          postType: _postType,
          draft: _draft && !_publishNow,
          publishNow: _publishNow,
          imageUrl: _imageUrl,
          workspacePath: widget.workspacePath,
        ),
      );
      if (!mounted) return;
      widget.onPublished?.call(result);
      setState(() {
        _notice = _publishNotice(result);
      });
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _error = error.toString().replaceFirst('Exception: ', ''),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _publishNotice(Map<String, dynamic> result) {
    final results = (result['results'] as List?) ?? const [];
    final failed = result['failed'] is num
        ? (result['failed'] as num).toInt()
        : results.whereType<Map>().where((item) => item['ok'] != true).length;
    if (results.length > 1 && failed > 0) {
      final firstError = results
          .whereType<Map>()
          .firstWhere(
            (item) => item['ok'] != true,
            orElse: () => const {},
          )['error']
          ?.toString();
      final detail = (firstError ?? '').isEmpty ? '' : ' $firstError';
      return '${results.length - failed} of ${results.length} channels accepted the post.$detail';
    }
    return _publishNow
        ? 'Published.'
        : _draft
        ? 'Draft saved.'
        : 'Queued in Buffer.';
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_BufferLoad>(
      future: _channelsFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const BoardSurface(
            child: Padding(
              padding: EdgeInsets.all(48),
              child: Center(child: CircularProgressIndicator()),
            ),
          );
        }
        if (snapshot.hasError || !snapshot.hasData) {
          final loadError = snapshot.error is _BufferLoadError
              ? snapshot.error as _BufferLoadError
              : null;
          final keyConfigured = loadError?.keyConfigured ?? false;
          final backendError =
              (loadError?.message ?? '${snapshot.error ?? 'Channels are unavailable.'}')
                  .replaceFirst('Exception: ', '');
          return BoardSurface(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  bufferDiagnosisTitle(keyConfigured: keyConfigured),
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: boardInk,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  bufferDiagnosisDetail(
                    keyConfigured: keyConfigured,
                    backendError: backendError,
                  ),
                  style: const TextStyle(color: boardMuted, fontSize: 13),
                ),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 8,
                  children: [
                    FilledButton(
                      onPressed: widget.onOpenSettings,
                      child: const Text('Open Settings'),
                    ),
                    OutlinedButton(
                      onPressed: _retryChannels,
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ],
            ),
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            BoardSurface(child: _channelsCard(snapshot.data!.channels)),
            const SizedBox(height: 16),
            BoardSurface(child: _suggestionsCard()),
            const SizedBox(height: 16),
            BoardSurface(child: _composerCard()),
          ],
        );
      },
    );
  }

  Widget _suggestionsCard() {
    final subtitle = _siteName.isEmpty
        ? 'Based on your connected site.'
        : 'Based on $_siteName.';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Expanded(
              child: Text(
                'Post ideas',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: boardInk,
                ),
              ),
            ),
            OutlinedButton.icon(
              onPressed: _ideasBusy ? null : _generateIdeas,
              icon: const Icon(Icons.auto_awesome_outlined, size: 16),
              label: Text(_ideasBusy ? 'Thinking…' : 'AI ideas'),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          '$subtitle Use one to fill the AI prompt below, or press AI ideas for fresh ones.',
          style: const TextStyle(color: boardMuted, fontSize: 12),
        ),
        const SizedBox(height: 8),
        if (_suggestionsLoading)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Center(
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          )
        else if (_suggestionsError != null)
          Row(
            children: [
              Expanded(
                child: Text(
                  _suggestionsError!,
                  style: const TextStyle(color: boardMuted, fontSize: 12),
                ),
              ),
              TextButton(
                onPressed: _loadSuggestions,
                child: const Text('Retry'),
              ),
            ],
          )
        else if (_suggestions.isEmpty)
          const Text(
            'No suggestions yet. Connect a site first, then come back for ideas.',
            style: TextStyle(color: boardMuted, fontSize: 12),
          )
        else
          for (final suggestion in _suggestions)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          suggestion['title']!,
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: boardInk,
                          ),
                        ),
                        Text(
                          suggestion['prompt']!,
                          style: const TextStyle(
                            fontSize: 12,
                            color: boardMuted,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton(
                    onPressed: () {
                      _promptController.text = suggestion['prompt']!;
                      setState(() {
                        _notice =
                            'Idea loaded into the AI prompt. Press Write with AI to draft it.';
                      });
                    },
                    child: const Text('Use'),
                  ),
                ],
              ),
            ),
      ],
    );
  }

  Widget _channelsCard(List<Map<String, dynamic>> channels) {
    if (channels.isEmpty) {
      return const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Channels',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w700,
              color: boardInk,
            ),
          ),
          SizedBox(height: 8),
          Text(
            'No Buffer channels found for this key.',
            style: TextStyle(color: boardMuted, fontSize: 13),
          ),
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Channels (${channels.length})',
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            color: boardInk,
          ),
        ),
        const SizedBox(height: 6),
        const Text(
          'Select where this post will go.',
          style: TextStyle(color: boardMuted, fontSize: 13),
        ),
        const SizedBox(height: 8),
        for (final channel in channels)
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            title: Text(
              channelLabel(channel),
              style: const TextStyle(fontSize: 13),
            ),
            value: _selectedChannels.contains(channel['id']?.toString()),
            onChanged: (selected) {
              final id = channel['id']?.toString();
              if (id == null || id.isEmpty) return;
              setState(() {
                if (selected == true) {
                  _selectedChannels.add(id);
                } else {
                  _selectedChannels.remove(id);
                }
              });
            },
          ),
      ],
    );
  }

  Widget _composerCard() => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Text(
        'Compose',
        style: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w700,
          color: boardInk,
        ),
      ),
      const SizedBox(height: 12),
      Row(
        children: [
          Expanded(
            child: TextField(
              controller: _promptController,
              onSubmitted: (_) => _generateText(),
              decoration: const InputDecoration(
                labelText: 'AI prompt (empty writes from your site)',
                hintText: 'Announce a new collection',
              ),
            ),
          ),
          const SizedBox(width: 8),
          OutlinedButton.icon(
            onPressed: _generating ? null : _generateText,
            icon: const Icon(Icons.auto_awesome_outlined, size: 16),
            label: const Text('Write with AI'),
          ),
        ],
      ),
      const SizedBox(height: 12),
      TextField(
        controller: _textController,
        minLines: 4,
        maxLines: 8,
        decoration: const InputDecoration(
          labelText: 'Post text',
          alignLabelWithHint: true,
        ),
      ),
      const SizedBox(height: 12),
      Row(
        children: [
          Expanded(
            child: DropdownButtonFormField<String>(
              initialValue: _postType,
              items: const [
                DropdownMenuItem(value: 'post', child: Text('Post')),
                DropdownMenuItem(value: 'story', child: Text('Story')),
                DropdownMenuItem(value: 'reel', child: Text('Reel')),
              ],
              onChanged: (value) =>
                  setState(() => _postType = value ?? 'post'),
              decoration: const InputDecoration(labelText: 'Type'),
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Draft', style: TextStyle(fontSize: 13)),
              value: _draft,
              onChanged: (value) => setState(() {
                _draft = value;
                if (value) _publishNow = false;
              }),
            ),
          ),
          Expanded(
            child: SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Publish now', style: TextStyle(fontSize: 13)),
              value: _publishNow,
              onChanged: (value) => setState(() {
                _publishNow = value;
                if (value) _draft = false;
              }),
            ),
          ),
        ],
      ),
      const SizedBox(height: 4),
      Row(
        children: [
          Expanded(
            child: TextField(
              controller: _imagePromptController,
              onSubmitted: (_) => _generateImage(),
              decoration: const InputDecoration(
                labelText: 'Image prompt',
                hintText: 'Sunset over the new storefront',
              ),
            ),
          ),
          const SizedBox(width: 8),
          OutlinedButton.icon(
            onPressed: _imageBusy ? null : _generateImage,
            icon: const Icon(Icons.brush_outlined, size: 16),
            label: Text(_generatingImage ? 'Painting…' : 'Generate image'),
          ),
        ],
      ),
      const SizedBox(height: 8),
      Row(
        children: [
          OutlinedButton.icon(
            onPressed: _imageBusy ? null : _chooseImage,
            icon: const Icon(Icons.image_outlined, size: 16),
            label: Text(
              _localImagePath == null ? 'Add image' : 'Change image',
            ),
          ),
          if (_localImagePath != null && !_imageBusy) ...[
            const SizedBox(width: 8),
            TextButton.icon(
              onPressed: _removeImage,
              icon: const Icon(Icons.close_rounded, size: 16),
              label: const Text('Remove'),
            ),
          ],
          if (_imageBusy) ...[
            const SizedBox(width: 12),
            const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            const SizedBox(width: 8),
            Text(
              _editingImage
                  ? 'Editing…'
                  : _generatingImage
                  ? 'Generating…'
                  : 'Uploading…',
              style: const TextStyle(color: boardMuted, fontSize: 12),
            ),
          ],
          if (_localImagePath != null && !_imageBusy) ...[
            const SizedBox(width: 12),
            Icon(
              _imageUrl != null
                  ? Icons.check_circle_outline_rounded
                  : Icons.hourglass_empty_rounded,
              size: 16,
              color: _imageUrl != null
                  ? const Color(0xFF1F9D55)
                  : const Color(0xFFB7791F),
            ),
            const SizedBox(width: 6),
            Text(
              socialImageStateLabel(
                hasImage: true,
                generated: _imageGenerated,
                pending: _imageUrl == null,
              ),
              style: const TextStyle(fontSize: 12, color: boardMuted),
            ),
          ],
        ],
      ),
      if (_localImagePath != null) ...[
        const SizedBox(height: 12),
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: Image.file(
            File(_localImagePath!),
            height: 180,
            fit: BoxFit.cover,
            errorBuilder: (context, error, stack) => const Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                'The selected image cannot be previewed.',
                style: TextStyle(color: boardMuted, fontSize: 12),
              ),
            ),
          ),
        ),
        if (_libraryImageUrl != null) ...[
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _imageEditController,
                  onSubmitted: (_) => _editImage(),
                  decoration: const InputDecoration(
                    labelText: 'Edit instruction',
                    hintText: 'Add a summer background',
                  ),
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton.icon(
                onPressed: _imageBusy ? null : _editImage,
                icon: const Icon(Icons.tune_outlined, size: 16),
                label: const Text('Edit with AI'),
              ),
            ],
          ),
        ],
      ],
      if (_error != null) ...[
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(11),
          decoration: BoxDecoration(
            color: const Color(0xFFB33142).withValues(alpha: .08),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(
            _error!,
            style: const TextStyle(color: Color(0xFFB33142), fontSize: 12),
          ),
        ),
      ],
      if (_notice != null) ...[
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(11),
          decoration: BoxDecoration(
            color: boardBlue.withValues(alpha: .08),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(
            _notice!,
            style: const TextStyle(color: Color(0xFF245A9C), fontSize: 12),
          ),
        ),
      ],
      const SizedBox(height: 14),
      ValueListenableBuilder<TextEditingValue>(
        valueListenable: _textController,
        builder: (context, value, _) => FilledButton.icon(
          onPressed:
              _selectedChannels.isEmpty ||
                  value.text.trim().isEmpty ||
                  _busy ||
                  _imageBusy
              ? null
              : _submit,
          icon: const Icon(Icons.send_outlined, size: 16),
          label: Text(
            _publishNow
                ? 'Publish now'
                : _draft
                ? 'Save draft'
                : 'Queue in Buffer',
          ),
        ),
      ),
    ],
  );
}
