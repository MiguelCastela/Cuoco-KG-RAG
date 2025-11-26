const RoundedInput = ({ placeholder, value, onChange, onKeyDown }) => {
  return (
    <input
      type="text"
      placeholder={placeholder}
      value={value}
      onChange={onChange}
      onKeyDown={onKeyDown}
      style={{
        border: "2px solid #eebeb3",
        borderRadius: "50px",
        padding: "16px 24px",
        outline: "none",
        fontSize: "24px",
        width: "50%",
        transition: "border-color 0.2s",
      }}
      onFocus={(e) => (e.target.style.borderColor = "#ff9990")}
      onBlur={(e) => (e.target.style.borderColor = "#eebeb3")}
    />
  );
};

export default RoundedInput;
