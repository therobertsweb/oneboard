import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'apple_design.dart';
import 'board_api.dart';

String formatImageSize(num bytes) {
  if (bytes < 1024) return '$bytes B';
  if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
  return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
}

const brandTextFields = [
  'business_name',
  'tagline',
  'services',
  'audience',
  'tone',
  'phone',
  'email',
  'address',
  'website',
  'notes',
];

const brandColorFields = ['primary', 'secondary', 'accent'];
const brandFontFields = ['headings', 'body'];

String brandFieldLabel(String key) {
  final words = key.replaceAll('_', ' ').split(' ');
  return words.map((w) => w.isEmpty ? w : w[0].toUpperCase() + w.substring(1)).join(' ');
}

/// Site & Brand: identity, full brand form, visible logo upload, and the
/// generated image library with thumbnails and downloads.
class SiteBrandPanel extends StatelessWidget {
  const SiteBrandPanel({
    super.key,
    required this.api,
    required this.site,
    required this.pickImage,
    required this.onChanged,
  });

  final BoardApi api;
  final Map<String, dynamic> site;
  final Future<String?> Function() pickImage;
  final Future<void> Function() onChanged;

  @override
  Widget build(BuildContext context) {
    final brand = (site['brand'] as Map?)?.cast<String, dynamic>() ?? {};
    final images = (site['images'] as List?)?.whereType<Map>().toList() ?? [];
    final canEdit = site['can_edit'] != false;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        BoardSurface(
          child: _IdentityCard(api: api, site: site, onChanged: onChanged),
        ),
        const SizedBox(height: 16),
        BoardSurface(
          child: _BrandCard(
            api: api,
            brand: brand,
            canEdit: canEdit,
            onChanged: onChanged,
          ),
        ),
        const SizedBox(height: 16),
        BoardSurface(
          child: _LogoCard(
            api: api,
            brand: brand,
            canEdit: canEdit,
            pickImage: pickImage,
            onChanged: onChanged,
          ),
        ),
        const SizedBox(height: 16),
        BoardSurface(
          child: _ImageLibraryCard(
            api: api,
            images: images,
            onChanged: onChanged,
          ),
        ),
      ],
    );
  }
}

class _IdentityCard extends StatefulWidget {
  const _IdentityCard({
    required this.api,
    required this.site,
    required this.onChanged,
  });

  final BoardApi api;
  final Map<String, dynamic> site;
  final Future<void> Function() onChanged;

  @override
  State<_IdentityCard> createState() => _IdentityCardState();
}

class _IdentityCardState extends State<_IdentityCard> {
  late final TextEditingController _displayName;
  late final TextEditingController _clientName;
  bool _busy = false;
  String? _error;
  String? _notice;

  @override
  void initState() {
    super.initState();
    _displayName = TextEditingController();
    _clientName = TextEditingController();
    _refill(widget.site);
  }

  @override
  void didUpdateWidget(covariant _IdentityCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.site, widget.site)) _refill(widget.site);
  }

  void _refill(Map<String, dynamic> site) {
    _displayName.text = site['display_name']?.toString() ?? '';
    _clientName.text = site['client_name']?.toString() ?? '';
  }

  @override
  void dispose() {
    _displayName.dispose();
    _clientName.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await widget.api.post('/api/site-manager/site', {
        'display_name': _displayName.text.trim(),
        'client_name': _clientName.text.trim(),
      });
      await widget.onChanged();
      if (!mounted) return;
      setState(() => _notice = 'Site identity saved.');
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _error = error.toString().replaceFirst('Exception: ', ''),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final canEdit = widget.site['can_edit'] != false;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Expanded(
              child: Text(
                'Site identity',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: boardInk,
                ),
              ),
            ),
            if (!canEdit)
              const Text(
                'View-only access',
                style: TextStyle(color: boardMuted, fontSize: 12),
              ),
          ],
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _displayName,
          enabled: !_busy && canEdit,
          decoration: const InputDecoration(labelText: 'Display name'),
        ),
        const SizedBox(height: 11),
        TextField(
          controller: _clientName,
          enabled: !_busy && canEdit,
          decoration: const InputDecoration(labelText: 'Client name'),
        ),
        if (_error != null) ...[
          const SizedBox(height: 12),
          _banner(_error!, true),
        ],
        if (_notice != null) ...[
          const SizedBox(height: 12),
          _banner(_notice!, false),
        ],
        const SizedBox(height: 14),
        FilledButton(
          onPressed: !_busy && canEdit ? _save : null,
          child: const Text('Save identity'),
        ),
      ],
    );
  }
}

Widget _banner(String message, bool isError) => Container(
  padding: const EdgeInsets.all(11),
  decoration: BoxDecoration(
    color: (isError ? const Color(0xFFB33142) : boardBlue).withValues(
      alpha: .08,
    ),
    borderRadius: BorderRadius.circular(10),
  ),
  child: Text(
    message,
    style: TextStyle(
      color: isError ? const Color(0xFFB33142) : const Color(0xFF245A9C),
      fontSize: 12,
    ),
  ),
);

class _BrandCard extends StatefulWidget {
  const _BrandCard({
    required this.api,
    required this.brand,
    required this.canEdit,
    required this.onChanged,
  });

  final BoardApi api;
  final Map<String, dynamic> brand;
  final bool canEdit;
  final Future<void> Function() onChanged;

  @override
  State<_BrandCard> createState() => _BrandCardState();
}

class _BrandCardState extends State<_BrandCard> {
  final _fields = <String, TextEditingController>{};
  final _colors = <String, TextEditingController>{};
  final _fonts = <String, TextEditingController>{};
  bool _busy = false;
  String? _error;
  String? _notice;

  @override
  void initState() {
    super.initState();
    for (final key in brandTextFields) {
      _fields[key] = TextEditingController();
    }
    for (final key in brandColorFields) {
      _colors[key] = TextEditingController();
    }
    for (final key in brandFontFields) {
      _fonts[key] = TextEditingController();
    }
    _refill(widget.brand);
  }

  @override
  void didUpdateWidget(covariant _BrandCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.brand, widget.brand)) _refill(widget.brand);
  }

  void _refill(Map<String, dynamic> brand) {
    for (final key in brandTextFields) {
      _fields[key]!.text = brand[key]?.toString() ?? '';
    }
    final colors = (brand['colors'] as Map?)?.cast<String, dynamic>() ?? {};
    for (final key in brandColorFields) {
      _colors[key]!.text = colors[key]?.toString() ?? '';
    }
    final fonts = (brand['fonts'] as Map?)?.cast<String, dynamic>() ?? {};
    for (final key in brandFontFields) {
      _fonts[key]!.text = fonts[key]?.toString() ?? '';
    }
  }

  @override
  void dispose() {
    for (final controller in [
      ..._fields.values,
      ..._colors.values,
      ..._fonts.values,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await widget.api.post('/api/site-manager/site', {
        'brand': {
          for (final entry in _fields.entries)
            entry.key: entry.value.text.trim(),
          'colors': {
            for (final entry in _colors.entries)
              entry.key: entry.value.text.trim(),
          },
          'fonts': {
            for (final entry in _fonts.entries)
              entry.key: entry.value.text.trim(),
          },
        },
      });
      await widget.onChanged();
      if (!mounted) return;
      setState(() => _notice = 'Brand details saved.');
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _error = error.toString().replaceFirst('Exception: ', ''),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Text(
        'Brand details',
        style: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w700,
          color: boardInk,
        ),
      ),
      const SizedBox(height: 12),
      for (final key in brandTextFields) ...[
        TextField(
          controller: _fields[key],
          enabled: !_busy,
          minLines: key == 'services' || key == 'notes' ? 2 : 1,
          maxLines: key == 'services' || key == 'notes' ? 4 : 1,
          decoration: InputDecoration(
            labelText: brandFieldLabel(key),
            alignLabelWithHint: true,
          ),
        ),
        const SizedBox(height: 11),
      ],
      const Text(
        'Colors',
        style: TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w600,
          color: boardInk,
        ),
      ),
      const SizedBox(height: 8),
      Row(
        children: [
          for (final key in brandColorFields) ...[
            Expanded(
              child: TextField(
                controller: _colors[key],
                enabled: !_busy,
                decoration: InputDecoration(
                  labelText: brandFieldLabel(key),
                  hintText: '#0A84FF',
                ),
              ),
            ),
            if (key != brandColorFields.last) const SizedBox(width: 10),
          ],
        ],
      ),
      const SizedBox(height: 11),
      const Text(
        'Fonts',
        style: TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w600,
          color: boardInk,
        ),
      ),
      const SizedBox(height: 8),
      Row(
        children: [
          for (final key in brandFontFields) ...[
            Expanded(
              child: TextField(
                controller: _fonts[key],
                enabled: !_busy,
                decoration: InputDecoration(labelText: brandFieldLabel(key)),
              ),
            ),
            if (key != brandFontFields.last) const SizedBox(width: 10),
          ],
        ],
      ),
      if (_error != null) ...[const SizedBox(height: 12), _banner(_error!, true)],
      if (_notice != null) ...[
        const SizedBox(height: 12),
        _banner(_notice!, false),
      ],
      const SizedBox(height: 14),
      FilledButton(
        onPressed: !_busy && widget.canEdit ? _save : null,
        child: const Text('Save brand'),
      ),
    ],
  );
}

class _LogoCard extends StatefulWidget {
  const _LogoCard({
    required this.api,
    required this.brand,
    required this.canEdit,
    required this.pickImage,
    required this.onChanged,
  });

  final BoardApi api;
  final Map<String, dynamic> brand;
  final bool canEdit;
  final Future<String?> Function() pickImage;
  final Future<void> Function() onChanged;

  @override
  State<_LogoCard> createState() => _LogoCardState();
}

class _LogoCardState extends State<_LogoCard> {
  bool _busy = false;
  String? _error;
  String? _notice;

  Future<void> _upload() async {
    final path = await widget.pickImage();
    if (path == null || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await widget.api.upload('/api/site-manager/site/logo', 'logo', path);
      await widget.onChanged();
      if (!mounted) return;
      setState(() => _notice = 'Logo updated.');
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _error = error.toString().replaceFirst('Exception: ', ''),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final logoUrl = widget.brand['logo_url']?.toString() ?? '';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Brand logo',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            color: boardInk,
          ),
        ),
        const SizedBox(height: 6),
        const Text(
          'PNG, JPEG, WebP, or GIF. Uploading replaces the current logo.',
          style: TextStyle(color: boardMuted, fontSize: 13),
        ),
        const SizedBox(height: 12),
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            _SiteImage(
              api: widget.api,
              url: logoUrl,
              width: 120,
              height: 120,
              emptyLabel: 'No logo yet',
            ),
            const SizedBox(width: 16),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: !_busy && widget.canEdit ? _upload : null,
                icon: const Icon(Icons.upload_outlined, size: 16),
                label: Text(logoUrl.isEmpty ? 'Upload logo' : 'Replace logo'),
              ),
            ),
          ],
        ),
        if (_error != null) ...[const SizedBox(height: 12), _banner(_error!, true)],
        if (_notice != null) ...[
          const SizedBox(height: 12),
          _banner(_notice!, false),
        ],
      ],
    );
  }
}

class _ImageLibraryCard extends StatefulWidget {
  const _ImageLibraryCard({
    required this.api,
    required this.images,
    required this.onChanged,
  });

  final BoardApi api;
  final List<Map> images;
  final Future<void> Function() onChanged;

  @override
  State<_ImageLibraryCard> createState() => _ImageLibraryCardState();
}

class _ImageLibraryCardState extends State<_ImageLibraryCard> {
  bool _busy = false;

  Future<void> _generate() async {
    final promptController = TextEditingController();
    var format = 'png';
    final prompt = await showDialog<String>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Generate site image'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: promptController,
                autofocus: true,
                minLines: 2,
                maxLines: 4,
                decoration: const InputDecoration(
                  labelText: 'Describe the image',
                  hintText: 'Modern storefront at sunset',
                ),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: format,
                items: const [
                  DropdownMenuItem(value: 'png', child: Text('PNG')),
                  DropdownMenuItem(value: 'jpg', child: Text('JPG')),
                  DropdownMenuItem(value: 'webp', child: Text('WebP')),
                ],
                onChanged: (value) =>
                    setDialogState(() => format = value ?? 'png'),
                decoration: const InputDecoration(labelText: 'Format'),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(
                context,
                promptController.text.trim().isEmpty
                    ? null
                    : promptController.text.trim(),
              ),
              child: const Text('Generate'),
            ),
          ],
        ),
      ),
    );
    promptController.dispose();
    if (prompt == null || !mounted) return;
    setState(() => _busy = true);
    try {
      await widget.api.post('/api/ai/images', {
        'prompt': prompt,
        'output_format': format,
      });
      await widget.onChanged();
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Site image generated.')));
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(error.toString().replaceFirst('Exception: ', '')),
        ),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'Image library (${widget.images.length})',
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: boardInk,
                ),
              ),
            ),
            OutlinedButton.icon(
              onPressed: _busy ? null : _generate,
              icon: const Icon(Icons.brush_outlined, size: 16),
              label: Text(_busy ? 'Painting…' : 'Generate'),
            ),
          ],
        ),
        const SizedBox(height: 6),
        const Text(
          'Images generated for this site. The same images can illustrate social posts from the Social section.',
          style: TextStyle(color: boardMuted, fontSize: 13),
        ),
        const SizedBox(height: 12),
        if (widget.images.isEmpty)
          const Text(
            'No generated images yet.',
            style: TextStyle(color: boardMuted, fontSize: 13),
          ),
        for (final image in widget.images) ...[
          _LibraryRow(api: widget.api, image: image.cast<String, dynamic>()),
          const SizedBox(height: 10),
        ],
      ],
    );
  }
}

class _LibraryRow extends StatefulWidget {
  const _LibraryRow({required this.api, required this.image});

  final BoardApi api;
  final Map<String, dynamic> image;

  @override
  State<_LibraryRow> createState() => _LibraryRowState();
}

class _LibraryRowState extends State<_LibraryRow> {
  bool _busy = false;

  Future<void> _download() async {
    final url = widget.image['url']?.toString() ?? '';
    if (url.isEmpty || _busy) return;
    setState(() => _busy = true);
    try {
      final bytes = await widget.api.getBytes(url);
      final home = Platform.environment['HOME'] ?? '/tmp';
      var name = widget.image['filename']?.toString().trim() ?? '';
      if (name.isEmpty) name = 'site-image.png';
      name = name.replaceAll(RegExp(r'[\\/:]'), '_');
      await File('$home/Downloads/$name').writeAsBytes(bytes);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Saved to Downloads/$name.')),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(error.toString().replaceFirst('Exception: ', '')),
        ),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final prompt = widget.image['prompt']?.toString() ?? '';
    final meta = [
      widget.image['created_at']?.toString() ?? '',
      formatImageSize((widget.image['size_bytes'] as num?) ?? 0),
    ].where((part) => part.isNotEmpty).join(' · ');
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFF9F9FB),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SiteImage(
            api: widget.api,
            url: widget.image['url']?.toString() ?? '',
            width: 96,
            height: 96,
            emptyLabel: 'No preview',
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  widget.image['filename']?.toString() ?? 'Image',
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: boardInk,
                  ),
                ),
                if (meta.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    meta,
                    style: const TextStyle(color: boardMuted, fontSize: 11),
                  ),
                ],
                if (prompt.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    prompt,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12, height: 1.45),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(width: 8),
          TextButton(
            onPressed: _busy ? null : _download,
            child: const Text('Download'),
          ),
        ],
      ),
    );
  }
}

/// Authenticated site image (logo or library thumbnail).
class _SiteImage extends StatefulWidget {
  const _SiteImage({
    required this.api,
    required this.url,
    required this.width,
    required this.height,
    required this.emptyLabel,
  });

  final BoardApi api;
  final String url;
  final double width;
  final double height;
  final String emptyLabel;

  @override
  State<_SiteImage> createState() => _SiteImageState();
}

class _SiteImageState extends State<_SiteImage> {
  late final Future<Uint8List?> _bytes;

  @override
  void initState() {
    super.initState();
    _bytes = _load();
  }

  Future<Uint8List?> _load() async {
    if (widget.url.isEmpty) return null;
    try {
      return await widget.api.getBytes(widget.url);
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: widget.width,
      height: widget.height,
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
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(8),
                child: Text(
                  widget.emptyLabel,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: boardMuted, fontSize: 11),
                ),
              ),
            );
          }
          return Image.memory(
            bytes,
            fit: BoxFit.cover,
            errorBuilder: (context, _, _) => Center(
              child: Text(
                widget.emptyLabel,
                textAlign: TextAlign.center,
                style: const TextStyle(color: boardMuted, fontSize: 11),
              ),
            ),
          );
        },
      ),
    );
  }
}
