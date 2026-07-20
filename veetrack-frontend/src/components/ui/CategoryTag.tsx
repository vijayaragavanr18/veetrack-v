interface CategoryTagProps {
  label: string;
}

export default function CategoryTag({ label }: CategoryTagProps) {
  return (
    <span className="inline-block px-2 py-0.5 rounded text-[10px] font-bold tracking-widest uppercase bg-black/60 text-white backdrop-blur-sm">
      {label.slice(0, 20)}
    </span>
  );
}
