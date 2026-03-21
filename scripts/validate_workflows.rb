#!/usr/bin/env ruby
# frozen_string_literal: true

require 'psych'

class WorkflowValidator
  def initialize(path)
    @path = path
    @errors = []
  end

  def validate!
    ast = Psych.parse_file(@path)
    raise 'Empty YAML document' if ast.nil?
    walk(ast)
    @errors
  rescue StandardError => e
    @errors << "#{@path}: #{e.message}"
    @errors
  end

  private

  def walk(node, breadcrumb = [])
    return if node.nil?

    if node.is_a?(Psych::Nodes::Mapping)
      seen = {}
      pairs = (node.children || []).each_slice(2).to_a
      pairs.each do |key_node, value_node|
        next unless key_node
        key = scalar_value(key_node)
        location = [@path, *breadcrumb, key].compact.join(' > ')
        @errors << "Duplicate key '#{key}' at #{location}" if seen[key]
        seen[key] = true
        walk(value_node, breadcrumb + [key])
      end
    elsif node.respond_to?(:children) && node.children
      node.children.each { |child| walk(child, breadcrumb) }
    end
  end

  def scalar_value(node)
    node.respond_to?(:value) ? node.value.to_s : node.class.name
  end
end

workflow_files = Dir.glob('.github/workflows/*.{yml,yaml}')
all_errors = workflow_files.flat_map { |path| WorkflowValidator.new(path).validate! }

if all_errors.empty?
  puts "Workflow validation passed for #{workflow_files.size} file(s)."
else
  warn all_errors.join("\n")
  exit 1
end
