import type { DateTile as DateTileValue } from "../types";

interface Props {
  tile: DateTileValue;
}

export function DateTile({ tile }: Props) {
  return (
    <div className="date-tile">
      <span className="date-tile__weekday">{tile.weekday}</span>
      <span className="date-tile__month-day">{tile.monthDay}</span>
    </div>
  );
}
