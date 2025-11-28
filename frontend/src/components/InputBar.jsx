const RoundedInput = ({ placeholder, value, onChange, onKeyDown }) => {
  return (
    <input
      type="text"
      placeholder={placeholder}
      value={value}
      onChange={onChange}
      onKeyDown={onKeyDown}
      style={{
        border: "2px solid #d3d3d3ff",
        borderRadius: "25px",
        padding: "16px 24px",
        outline: "none",
        fontSize: "24px",
        width: "100%",
        transition: "border-color 0.2s",
      }}
      onFocus={(e) => (e.target.style.borderColor = "#a1a1a1ff")}
      onBlur={(e) => (e.target.style.borderColor = "#c0c0c0ff")}
    />
  );
};

export default RoundedInput;
