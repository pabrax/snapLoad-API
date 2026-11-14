"""
Escritura de tags y portada con mutagen, y limpieza de título/artista para buscar en MusicBrainz.

Solo toca los tags: el stream de audio no se recodifica ni se modifica. Un valor ausente nunca borra
un tag que el archivo ya tenga. Un archivo no soportado (wav) o ilegible devuelve False sin lanzar.
"""
import base64
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class TagData:
    """Tags a escribir; None = no tocar ese campo."""
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    year: Optional[str] = None
    track_no: Optional[int] = None
    mb_recording_id: Optional[str] = None
    mb_release_id: Optional[str] = None


# --- limpieza -------------------------------------------------------------------------------------

_NOISE = re.compile(
    r"\s*[\(\[]\s*(?:official\s+(?:music\s+)?(?:video|audio|lyric\s+video|visualizer)|lyrics?|lyric\s+video|"
    r"music\s+video|audio|video|visualizer|hd|hq|4k|full\s+(?:video|song|album))\s*[\)\]]",
    re.IGNORECASE,
)


def clean_artist(raw: Optional[str]) -> Optional[str]:
    """Quita los sufijos de canal de YouTube (" - Topic", "VEVO"); None si queda vacío."""
    if not raw or not raw.strip():
        return None
    name = raw.strip()
    name = re.sub(r"\s+-\s+Topic$", "", name, flags=re.IGNORECASE)
    stripped = re.sub(r"\s*vevo$", "", name, flags=re.IGNORECASE)
    return (stripped.strip() or name) if name.lower() != "topic" else name


def clean_title(raw: Optional[str], artist: Optional[str] = None) -> Optional[str]:
    """
    Quita el ruido de un título de YouTube ("(Official Video)", "[Lyrics]", "[4K]") y el prefijo
    "Artista - ". Conserva lo que cambia la canción ((feat. X), (Live), (Remastered)). Nunca devuelve vacío.
    """
    if not raw or not raw.strip():
        return raw
    original = raw.strip()
    title = original
    while True:
        cleaned = _NOISE.sub("", title)
        if cleaned == title:
            break
        title = cleaned
    title = title.strip()
    if artist:
        name = artist.strip().lower()
        if title.lower().startswith(f"{name} - "):
            title = title[len(name) + 3:].strip()
        elif title.lower().endswith(f" - {name}"):
            title = title[: -(len(name) + 3)].strip()
    return title or original


# --- escritura ------------------------------------------------------------------------------------


def _image_mime(data: bytes) -> str:
    return "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def _vorbis_fields(data: TagData) -> dict:
    fields = {
        "title": data.title, "artist": data.artist, "album": data.album, "date": data.year,
        "tracknumber": str(data.track_no) if data.track_no else None,
        "musicbrainz_trackid": data.mb_recording_id, "musicbrainz_albumid": data.mb_release_id,
    }
    return {k: [v] for k, v in fields.items() if v}


def _write_mp3(path: Path, data: TagData, cover: Optional[bytes]) -> None:
    from mutagen.id3 import APIC, ID3, TALB, TDRC, TIT2, TPE1, TRCK, TXXX, UFID, ID3NoHeaderError

    try:
        tags = ID3(str(path))
    except ID3NoHeaderError:
        tags = ID3()
    for frame, value in ((TIT2, data.title), (TPE1, data.artist), (TALB, data.album), (TDRC, data.year)):
        if value:
            tags.setall(frame.__name__, [frame(encoding=3, text=value)])
    if data.track_no:
        tags.setall("TRCK", [TRCK(encoding=3, text=str(data.track_no))])
    if data.mb_recording_id:
        tags.setall("UFID:http://musicbrainz.org",
                    [UFID(owner="http://musicbrainz.org", data=data.mb_recording_id.encode("ascii"))])
    if data.mb_release_id:
        tags.setall("TXXX:MusicBrainz Album Id",
                    [TXXX(encoding=3, desc="MusicBrainz Album Id", text=data.mb_release_id)])
    if cover:
        tags.delall("APIC")
        tags.add(APIC(encoding=3, mime=_image_mime(cover), type=3, desc="Cover", data=cover))
    tags.save(str(path), v2_version=3)


def _write_m4a(path: Path, data: TagData, cover: Optional[bytes]) -> None:
    from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm

    audio = MP4(str(path))
    if audio.tags is None:
        audio.add_tags()
    t = audio.tags
    for key, value in (("\xa9nam", data.title), ("\xa9ART", data.artist), ("\xa9alb", data.album),
                       ("\xa9day", data.year)):
        if value:
            t[key] = [value]
    if data.track_no:
        t["trkn"] = [(data.track_no, 0)]
    for name, value in (("MusicBrainz Track Id", data.mb_recording_id),
                        ("MusicBrainz Album Id", data.mb_release_id)):
        if value:
            t[f"----:com.apple.iTunes:{name}"] = [MP4FreeForm(value.encode("ascii"))]
    if cover:
        fmt = MP4Cover.FORMAT_PNG if _image_mime(cover) == "image/png" else MP4Cover.FORMAT_JPEG
        t["covr"] = [MP4Cover(cover, imageformat=fmt)]
    audio.save()


def _write_vorbis_like(path: Path, data: TagData, cover: Optional[bytes], kind: str) -> None:
    from mutagen.flac import FLAC, Picture
    from mutagen.oggopus import OggOpus
    from mutagen.oggvorbis import OggVorbis

    audio = {"flac": FLAC, "ogg": OggVorbis, "opus": OggOpus}[kind](str(path))
    if audio.tags is None:
        audio.add_tags()
    for key, value in _vorbis_fields(data).items():
        audio[key] = value
    if cover:
        picture = Picture()
        picture.type, picture.mime, picture.data = 3, _image_mime(cover), cover
        if kind == "flac":
            audio.clear_pictures()
            audio.add_picture(picture)
        else:
            audio["metadata_block_picture"] = [base64.b64encode(picture.write()).decode("ascii")]
    audio.save()


_WRITERS = {
    ".mp3": _write_mp3,
    ".m4a": _write_m4a,
    ".flac": lambda p, d, c: _write_vorbis_like(p, d, c, "flac"),
    ".ogg": lambda p, d, c: _write_vorbis_like(p, d, c, "ogg"),
    ".opus": lambda p, d, c: _write_vorbis_like(p, d, c, "opus"),
}


def write_tags(path: Path, data: TagData, cover: Optional[bytes] = None) -> bool:
    """
    Escribe tags (y portada, que sustituye a la anterior) en un audio sin tocar el stream.

    Returns:
        True si se escribió; False si el formato no admite tags (wav, aac suelto), el archivo no
        existe o es ilegible
    """
    path = Path(path)
    writer = _WRITERS.get(path.suffix.lower())
    if writer is None or not path.is_file():
        return False
    try:
        writer(path, data, cover)
        return True
    except Exception:
        return False


def write_replaygain(path: Path, loudness_lufs: float) -> bool:
    """
    Escribe la ganancia de pista como tag (sin recodificar ni tocar el audio): `REPLAYGAIN_TRACK_GAIN`
    (referencia -18 LUFS) o, en Ogg Opus, `R128_TRACK_GAIN` en Q7.8 dB respecto a -23 LUFS.

    Returns:
        True si se escribió; False si el formato no admite tags, falta el archivo o es ilegible
    """
    from .audio_quality import R128_REFERENCE_LUFS, replaygain_db

    path = Path(path)
    ext = path.suffix.lower()
    if ext not in _WRITERS or not path.is_file():
        return False
    gain_text = f"{replaygain_db(loudness_lufs):+.2f} dB"
    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3, TXXX, ID3NoHeaderError
            try:
                tags = ID3(str(path))
            except ID3NoHeaderError:
                tags = ID3()
            tags.setall("TXXX:REPLAYGAIN_TRACK_GAIN",
                        [TXXX(encoding=3, desc="REPLAYGAIN_TRACK_GAIN", text=gain_text)])
            tags.save(str(path), v2_version=3)
        elif ext == ".m4a":
            from mutagen.mp4 import MP4, MP4FreeForm
            audio = MP4(str(path))
            if audio.tags is None:
                audio.add_tags()
            audio.tags["----:com.apple.iTunes:REPLAYGAIN_TRACK_GAIN"] = [MP4FreeForm(gain_text.encode("ascii"))]
            audio.save()
        else:
            from mutagen.flac import FLAC
            from mutagen.oggopus import OggOpus
            from mutagen.oggvorbis import OggVorbis
            audio = {".flac": FLAC, ".ogg": OggVorbis, ".opus": OggOpus}[ext](str(path))
            if audio.tags is None:
                audio.add_tags()
            if ext == ".opus":
                audio["R128_TRACK_GAIN"] = [str(round((R128_REFERENCE_LUFS - loudness_lufs) * 256))]
            else:
                audio["REPLAYGAIN_TRACK_GAIN"] = [gain_text]
            audio.save()
        return True
    except Exception:
        return False
