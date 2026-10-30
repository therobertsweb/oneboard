import 'dart:io';

import 'package:flutter/material.dart';

import 'apple_design.dart';
import 'board_api.dart';

const requestStatuses = ['open', 'in_review', 'proposed', 'done'];

String requestTitle(Map<String, dynamic> request) {
  for (final key in ['client_name', 'page', 'text', 'message']) {
    final value = request[key]?.toString().trim() ?? '';
    if (value.isNotEmpty) return value.length > 90 ? '${value.substring(0, 90)}…' : value;
  }
  return 'Request ${request['id'] ?? ''}';
}

Color requestStatusColor(String status) => switch (status) {
  'done' => const Color(0xFF1F9D55),
  'in_review' || 'proposed' => boardBlue,
  _ => const Color(0xFFB25E09),
};

/// Full request thread: client context, attachments with download,
/// conversation, comment composer, status, and delete.
class RequestThreadView extends StatefulWidget {
  const RequestThreadView({
    super.key,
    required this.api,
    required this.requestId,
    required this.workspacePath,
    required this.onChanged,
  });

  final BoardApi api;
  final int requestId;
  final String workspacePath;
  final Future<void> Function() onChanged;

  @override
  State<RequestThreadView> createState() => _RequestThreadViewState();
}

class _RequestThreadViewState extends State<RequestThreadView> {
  late Future<Map<String, dynamic>> _threadFuture;
  late final TextEditingController _commentController;
  String? _actionError;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _commentController = TextEditingController();
    _threadFuture = _load();
  }

  @override
  void dispose() {
    _commentController.dispose();
    super.dispose();
  }

  Future<Map<String, dynamic>> _load() async {
    final response = await widget.api.get(
      '/api/site-manager/requests/${widget.requestId}',
    );
    return response;
  }

  void _reload() => setState(() => _threadFuture = _load());

  Map<String, dynamic> _payload(Map<String, dynamic> extra) => {
    ...extra,
    if (widget.workspacePath.isNotEmpty)
      'expected_directory_path': widget.workspacePath,
  };

  Future<void> _comment() async {
    final body = _commentController.text.trim();
    if (body.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _actionError = null;
    });
    try {
      await widget.api.post(
        '/api/site-manager/requests/${widget.requestId}/comments',
        _payload({'body': body}),
      );
      await widget.onChanged();
      if (!mounted) return;
      setState(() {
        _commentController.clear();
        _threadFuture = _load();
      });
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _actionError = error.toString().replaceFirst('Exception: ', ''),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _setStatus(String status) async {
    setState(() {
      _busy = true;
      _actionError = null;
    });
    try {
      await widget.api.post(
        '/api/site-manager/requests/${widget.requestId}/status',
        _payload({'status': status}),
      );
      await widget.onChanged();
      if (!mounted) return;
      setState(() => _threadFuture = _load());
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _actionError = error.toString().replaceFirst('Exception: ', ''),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete request?'),
        content: const Text('This removes the request and its conversation.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _busy = true;
      _actionError = null;
    });
    try {
      await widget.api.call(
        'DELETE',
        '/api/site-manager/requests/${widget.requestId}',
      );
      await widget.onChanged();
      if (!mounted) return;
      Navigator.pop(context);
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _actionError = error.toString().replaceFirst('Exception: ', ''),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _download(Map<String, dynamic> attachment) async {
    final filename = attachment['filename']?.toString() ?? '';
    if (filename.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _actionError = null;
    });
    try {
      final bytes = await widget.api.getBytes(
        '/site-manager/requests/attachments/${Uri.encodeComponent(filename)}',
      );
      final home = Platform.environment['HOME'] ?? '/tmp';
      var name = attachment['original_name']?.toString().trim() ?? '';
      if (name.isEmpty) name = filename;
      name = name.replaceAll(RegExp(r'[\\/:]'), '_');
      final file = File('$home/Downloads/$name');
      await file.writeAsBytes(bytes);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Saved to Downloads/$name.')),
      );
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _actionError = error.toString().replaceFirst('Exception: ', ''),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

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
                      tooltip: 'Back to requests',
                      onPressed: () => Navigator.pop(context),
                      icon: const Icon(Icons.arrow_back_rounded),
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        'Request ${widget.requestId}',
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: boardInk,
                        ),
                      ),
                    ),
                    IconButton(
                      tooltip: 'Delete request',
                      onPressed: _busy ? null : _delete,
                      icon: const Icon(
                        Icons.delete_outline_rounded,
                        color: Color(0xFFB33142),
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(20, 10, 20, 24),
                  child: FutureBuilder<Map<String, dynamic>>(
                    future: _threadFuture,
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
                                'Could not open this request.',
                                style: TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.w600,
                                  color: boardInk,
                                ),
                              ),
                              const SizedBox(height: 8),
                              Text(
                                '${snapshot.error ?? 'Unknown error'}'
                                    .replaceFirst('Exception: ', ''),
                                style: const TextStyle(
                                  color: boardMuted,
                                  fontSize: 13,
                                ),
                              ),
                              const SizedBox(height: 14),
                              OutlinedButton.icon(
                                onPressed: _reload,
                                icon: const Icon(
                                  Icons.refresh_rounded,
                                  size: 16,
                                ),
                                label: const Text('Retry'),
                              ),
                            ],
                          ),
                        );
                      }
                      return _threadBody(snapshot.data!);
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

  Widget _threadBody(Map<String, dynamic> thread) {
    final status = thread['status']?.toString() ?? 'open';
    final comments =
        (thread['comments'] as List?)?.whereType<Map>().toList() ?? [];
    final attachments =
        (thread['attachments'] as List?)?.whereType<Map>().toList() ?? [];
    final contextLines = <String, String>{};
    for (final key in [
      'client_name',
      'page',
      'selector',
      'tag',
      'text',
      'message',
      'created_at',
      'updated_at',
    ]) {
      final value = thread[key]?.toString().trim() ?? '';
      if (value.isNotEmpty) contextLines[key] = value;
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        BoardSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 9,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: requestStatusColor(
                        status,
                      ).withValues(alpha: .12),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      status.toUpperCase(),
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                        color: requestStatusColor(status),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      requestTitle(thread),
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        color: boardInk,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              for (final entry in contextLines.entries)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                        width: 110,
                        child: Text(
                          entry.key.replaceAll('_', ' '),
                          style: const TextStyle(
                            color: boardMuted,
                            fontSize: 12,
                          ),
                        ),
                      ),
                      Expanded(
                        child: SelectableText(
                          entry.value,
                          style: const TextStyle(fontSize: 13, height: 1.5),
                        ),
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 10),
              DropdownButtonFormField<String>(
                initialValue: requestStatuses.contains(status) ? status : null,
                hint: const Text('Status'),
                items: [
                  for (final option in requestStatuses)
                    DropdownMenuItem(
                      value: option,
                      child: Text(option.replaceAll('_', ' ')),
                    ),
                ],
                onChanged: _busy
                    ? null
                    : (value) {
                        if (value != null && value != status) _setStatus(value);
                      },
                decoration: const InputDecoration(labelText: 'Status'),
              ),
            ],
          ),
        ),
        if (attachments.isNotEmpty) ...[
          const SizedBox(height: 16),
          BoardSurface(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Attachments (${attachments.length})',
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: boardInk,
                  ),
                ),
                const SizedBox(height: 8),
                for (final item in attachments)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.attach_file_rounded,
                          size: 16,
                          color: boardMuted,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            item['original_name']?.toString().isNotEmpty == true
                                ? item['original_name'].toString()
                                : item['filename']?.toString() ?? 'File',
                            style: const TextStyle(fontSize: 13),
                          ),
                        ),
                        TextButton(
                          onPressed: _busy
                              ? null
                              : () => _download(item.cast<String, dynamic>()),
                          child: const Text('Download'),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
        const SizedBox(height: 16),
        BoardSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Conversation (${comments.length})',
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  color: boardInk,
                ),
              ),
              const SizedBox(height: 8),
              if (comments.isEmpty)
                const Text(
                  'No comments yet.',
                  style: TextStyle(color: boardMuted, fontSize: 13),
                ),
              for (final item in comments)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(11),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF9F9FB),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          [
                            item['author_name']?.toString() ?? '',
                            item['side']?.toString() ?? '',
                            item['created_at']?.toString() ?? '',
                          ].where((part) => part.isNotEmpty).join(' · '),
                          style: const TextStyle(
                            color: boardMuted,
                            fontSize: 11,
                          ),
                        ),
                        const SizedBox(height: 4),
                        SelectableText(
                          item['body']?.toString() ?? '',
                          style: const TextStyle(fontSize: 13, height: 1.5),
                        ),
                      ],
                    ),
                  ),
                ),
              const SizedBox(height: 6),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _commentController,
                      onSubmitted: (_) => _comment(),
                      decoration: const InputDecoration(
                        labelText: 'Write a comment',
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: _busy ? null : _comment,
                    child: const Text('Send'),
                  ),
                ],
              ),
              if (_actionError != null) ...[
                const SizedBox(height: 10),
                Text(
                  _actionError!,
                  style: const TextStyle(
                    color: Color(0xFFB33142),
                    fontSize: 12,
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
