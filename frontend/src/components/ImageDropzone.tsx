import { useCallback, useEffect, useRef, useState } from 'react';

import { ACCEPTED_TYPES, describeUploadProblem } from '../lib/uploadCheck';

interface ImageDropzoneProps {
  file: File | null;
  onSelect: (file: File) => void;
  onReject: (message: string) => void;
}

export function ImageDropzone({ file, onSelect, onReject }: ImageDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const accept = useCallback(
    (candidate: File | undefined) => {
      if (!candidate) return;
      const problem = describeUploadProblem(candidate);
      if (problem) {
        onReject(problem);
        return;
      }
      onSelect(candidate);
    },
    [onSelect, onReject],
  );

  return (
    <div>
      <div
        className={`dropzone${dragging ? ' dropzone--active' : ''}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          accept(event.dataTransfer.files[0]);
        }}
      >
        <p className="dropzone__headline">Bild hierher ziehen</p>
        <p className="dropzone__hint">PNG, JPG oder WebP, hoechstens 20 MB</p>
        <button type="button" onClick={() => inputRef.current?.click()}>
          Datei auswaehlen
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(',')}
          className="visually-hidden"
          aria-label="Bilddatei auswaehlen"
          onChange={(event) => {
            accept(event.target.files?.[0]);
            event.target.value = '';
          }}
        />
      </div>

      {file && previewUrl ? (
        <figure className="original-preview">
          <div className="checkerboard">
            <img src={previewUrl} alt={`Originalbild ${file.name}`} />
          </div>
          <figcaption>
            {file.name} - {(file.size / 1024).toFixed(0)} KB
          </figcaption>
        </figure>
      ) : null}
    </div>
  );
}
